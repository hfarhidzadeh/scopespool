"""Process isolation: serve a store to untrusted clients over a local Unix socket.

The server process owns the SQLite file (and the key file, if any). Clients
never touch them: they send one JSON request per line over a Unix domain
socket and get one JSON response per line. Every request carries a signed
member token (``dynmemory.auth``); the server verifies it and runs the request
as that member, through a reader bound to the verified audience or a writer
bound to the verified member. Administrative calls (admins, memberships,
delegation, pruning, rebuilding, reads without an audience) are not exposed.
A member may opt their own search into private retention
(``record_private_access``) and list their own retained memories
(``list_retained_memories``). Both act for the token's member alone and refuse
an audience, so a client never chooses whose activity is recorded or listed.

The socket file is created with owner-only permissions (0600), so the
operating system also limits who can connect. Run the server as its own user
and give clients tokens, not file access.

Request:  {"token": "...", "op": "search", "args": {"query": "launch"},
           "audience": ["<token of another viewer>", ...]}
Response: {"ok": true, "result": ...}  or  {"ok": false, "error": "..."}

Standard library only. Unix domain sockets are needed (macOS, Linux).
"""

from __future__ import annotations

import dataclasses
import json
import os
import socket
import socketserver
import stat
from enum import Enum
from pathlib import Path
from typing import Optional, Union

from .auth import AuthenticationError, TokenAuthority
from .store import MemoryStore

#: Reads run as the verified audience; each lists the arguments a client may pass.
READS = {
    # Never a shared access; private tracking records only for the token's member.
    "search": ("query", "kind", "limit", "record_private_access"),
    "get_memory": ("memory_id",),
    "history": ("memory_id",),
    "list_memories": ("include_archived", "limit"),
    "get_message": ("message_id",),
    "sources_of": ("memory_id",),
    "disputes": ("channel", "memory_key"),
    "who_knows": ("memory_id",),
    "list_retained_memories": ("limit",),
}
#: Reads of the token's member's own private state; they take no audience.
OWN_READS = frozenset({"list_retained_memories"})
#: Writes run as the verified member.
WRITES = {
    "add_message": ("content", "channel"),
    "add_memory": (
        "content", "kind", "channel", "memory_key", "fact_subject",
        "source_message_ids", "confidence", "importance", "source",
    ),
    "retract_message": ("message_id",),
    "acknowledge": ("message_id", "kind"),
}
MAX_REQUEST_BYTES = 1 << 20
#: macOS allows 104 bytes for a socket path, Linux 108.
MAX_SOCKET_PATH = 100


def to_json(value):
    """Data classes, enums and tuples as plain JSON values."""
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {field.name: to_json(getattr(value, field.name)) for field in dataclasses.fields(value)}
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (list, tuple)):
        return [to_json(item) for item in value]
    if isinstance(value, dict):
        return {key: to_json(item) for key, item in value.items()}
    return value


def handle_request(store: MemoryStore, authority: TokenAuthority, request: object) -> dict:
    """Verify, authorise and run one request; never raises."""
    try:
        if not isinstance(request, dict):
            raise ValueError("a request must be a JSON object")
        member = authority.verify(request.get("token"))
        operation = request.get("op")
        arguments = request.get("args", {})
        if not isinstance(arguments, dict):
            raise ValueError("args must be an object")
        allowed = READS.get(operation) or WRITES.get(operation)
        if allowed is None:
            raise ValueError("unknown operation")
        unexpected = sorted(set(arguments) - set(allowed))
        if unexpected:
            raise ValueError("unexpected argument: {}".format(unexpected[0]))
        if operation in READS:
            audience = request.get("audience", [])
            if not isinstance(audience, list):
                raise ValueError("audience must be a list of tokens")
            private = arguments.get("record_private_access", False)
            if not isinstance(private, bool):
                raise ValueError("record_private_access must be true or false")
            if audience and (private or operation in OWN_READS):
                raise ValueError(
                    "private retention is for the token's member only and takes no audience"
                )
            viewers = [member] + [authority.verify(token) for token in audience]
            target = store.for_viewers(viewers)
        else:
            target = store.for_writer(member)
        result = getattr(target, operation)(**arguments)
        return {"ok": True, "result": to_json(result)}
    except AuthenticationError:
        return {"ok": False, "error": "authentication failed"}
    except TypeError:
        return {"ok": False, "error": "bad arguments"}
    except ValueError as error:
        return {"ok": False, "error": str(error)}
    except Exception:  # never reveal internals to a client
        return {"ok": False, "error": "internal error"}


class _Handler(socketserver.StreamRequestHandler):
    def setup(self) -> None:
        # Bounds each socket wait; store work between reads is not timed.
        self.timeout = self.server.idle_timeout
        super().setup()

    def handle(self) -> None:
        while True:
            try:
                line = self.rfile.readline(MAX_REQUEST_BYTES + 1)
            except socket.timeout:
                return
            if not line:
                return
            if len(line) > MAX_REQUEST_BYTES:
                self._send({"ok": False, "error": "request too large"})
                return
            try:
                request = json.loads(line.decode("utf-8"))
            except ValueError:
                response = {"ok": False, "error": "invalid JSON"}
            else:
                response = handle_request(self.server.store, self.server.authority, request)
            self._send(response)

    def _send(self, response: dict) -> None:
        self.wfile.write(json.dumps(response).encode("utf-8") + b"\n")
        self.wfile.flush()


class ScopeSpoolServer(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    """A threaded Unix-socket server for one store."""

    daemon_threads = True
    # The client opens a connection per call; while request threads hold the
    # GIL the accept loop lags, and socketserver's default queue of 5 refused
    # calls from 8 concurrent members (experiments/private_retention_socket.py).
    request_queue_size = socket.SOMAXCONN
    # Seconds a connection may wait between requests before it is closed, so
    # an idle client cannot hold a thread forever.
    idle_timeout: Optional[float] = 300.0

    def __init__(
        self,
        socket_path: Union[str, Path],
        store: MemoryStore,
        authority: TokenAuthority,
        *,
        idle_timeout: Optional[float] = None,
    ) -> None:
        if idle_timeout is not None:
            if idle_timeout <= 0:
                raise ValueError("idle_timeout must be positive")
            self.idle_timeout = idle_timeout
        path = str(Path(socket_path))
        if len(path.encode("utf-8")) > MAX_SOCKET_PATH:
            raise ValueError("socket path is too long for a Unix socket")
        if os.path.exists(path):
            raise FileExistsError("socket path already exists: {}".format(path))
        self.store = store
        self.authority = authority
        previous = os.umask(0o177)
        try:
            super().__init__(path, _Handler)
        finally:
            os.umask(previous)
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
        self.socket_path = path

    def server_close(self) -> None:
        super().server_close()
        try:
            os.unlink(self.socket_path)
        except FileNotFoundError:
            pass


class RemoteError(ValueError):
    """The server refused a request."""


class ScopeSpoolClient:
    """Call a ``ScopeSpoolServer`` as one member, optionally with more viewers."""

    def __init__(self, socket_path: Union[str, Path], token: str, *, timeout: float = 10.0) -> None:
        self.socket_path = str(socket_path)
        self.token = token
        self.timeout = timeout

    def call(self, operation: str, *, audience: Optional[list] = None, **arguments):
        request = {"token": self.token, "op": operation, "args": arguments}
        if audience:
            request["audience"] = list(audience)
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.settimeout(self.timeout)
            connection.connect(self.socket_path)
            connection.sendall(json.dumps(request).encode("utf-8") + b"\n")
            with connection.makefile("rb") as stream:
                line = stream.readline(MAX_REQUEST_BYTES * 8)
        response = json.loads(line.decode("utf-8"))
        if not response.get("ok"):
            raise RemoteError(response.get("error", "request failed"))
        return response["result"]

    def search(self, query: str, **arguments):
        return self.call("search", query=query, **arguments)

    def list_retained_memories(self, *, limit: int = 100):
        return self.call("list_retained_memories", limit=limit)

    def add_message(self, content: str, *, channel: str):
        return self.call("add_message", content=content, channel=channel)

    def add_memory(self, content: str, kind: str, *, channel: str, **arguments):
        return self.call("add_memory", content=content, kind=kind, channel=channel, **arguments)

    def retract_message(self, message_id: str):
        return self.call("retract_message", message_id=message_id)


# The earlier names, kept so existing code keeps working.
MemvaneServer = ScopeSpoolServer
MemvaneClient = ScopeSpoolClient
