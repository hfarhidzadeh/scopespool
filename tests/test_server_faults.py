"""Fault checks for the Unix-socket server: malformed input, slow clients, disconnects.

Each check pairs the fault with a control: a well-formed request that must
succeed, a setting under which the fault must not trigger, or a forced failure
that the detector must catch. A passing check therefore says the server did
the right thing, not merely that nothing was observed.
"""

import json
import re
import shutil
import socket
import struct
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from dynmemory import MemoryStore
from dynmemory.auth import TokenAuthority
from dynmemory.server import (
    MAX_REQUEST_BYTES, READS, STRING_ARGUMENTS, WRITES, ScopeSpoolClient, ScopeSpoolServer,
)


def short_directory():
    """A temporary folder short enough for a Unix socket path."""
    base = tempfile.gettempdir()
    return Path(tempfile.mkdtemp(prefix="ss", dir=base if len(base) < 60 else "/tmp"))


def handler_threads():
    """Live request-handler threads in this process."""
    return [
        thread for thread in threading.enumerate()
        if getattr(thread, "_target", None) is not None
        and getattr(thread._target, "__name__", "") == "process_request_thread"
    ]


def wait_until(condition, timeout):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.02)
    return condition()


#: Anything that would hint at server internals in a client-facing error.
LEAK = re.compile(r"Traceback|File \"|/|\\|Error\b|sqlite", re.IGNORECASE)


class ServerHarness(unittest.TestCase):
    """A running server whose handler failures are recorded, not printed."""

    TIMEOUT = 5.0

    def setUp(self):
        self.directory = short_directory()
        self.addCleanup(shutil.rmtree, self.directory, True)
        self.store = MemoryStore(self.directory / "s.sqlite3")
        self.store.join_channel("design", "alice")
        self.authority = TokenAuthority(TokenAuthority.generate_secret())
        self.token = self.authority.issue("alice")
        self.socket_path = self.directory / "s.sock"
        # Handler threads left by other tests, so counts here are relative.
        self.baseline = len(handler_threads())
        self.server = self.start_server(self.TIMEOUT)

    def start_server(self, idle_timeout, name="s.sock"):
        server = ScopeSpoolServer(
            self.directory / name, self.store, self.authority, idle_timeout=idle_timeout
        )
        server.handler_failures = []
        # socketserver prints a traceback to stderr for any exception that
        # escapes a handler; record those instead so a test can assert none.
        server.handle_error = lambda request, address: server.handler_failures.append(
            __import__("sys").exc_info()[1]
        )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return server

    def handlers_done(self):
        return len(handler_threads()) <= self.baseline

    def connect(self, path=None, timeout=5.0):
        connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.addCleanup(connection.close)
        connection.settimeout(timeout)
        connection.connect(str(path or self.socket_path))
        return connection

    def request_line(self, op="search", **arguments):
        if op == "search" and not arguments:
            arguments = {"query": "launch"}
        return json.dumps({"token": self.token, "op": op, "args": arguments}).encode() + b"\n"

    def exchange(self, raw, connection=None):
        """Send raw bytes on a connection and read one response line."""
        connection = connection or self.connect()
        connection.sendall(raw)
        reader = connection.makefile("rb")
        self.addCleanup(reader.close)
        line = reader.readline()
        return json.loads(line.decode("utf-8")) if line else None

    def assertServing(self):
        """Control: a fresh, well-formed call still succeeds."""
        client = ScopeSpoolClient(self.socket_path, self.token, timeout=5)
        self.assertIsInstance(client.search("launch"), list)

    def assertClientError(self, response, expected=None):
        self.assertIsNotNone(response, "the server closed without answering")
        self.assertIs(response["ok"], False)
        self.assertNotEqual(response["error"], "internal error")
        self.assertIsNone(LEAK.search(response["error"]), response["error"])
        if expected is not None:
            self.assertEqual(response["error"], expected)


@unittest.skipUnless(hasattr(socket, "AF_UNIX"), "Unix domain sockets are not available")
class MalformedInputTests(ServerHarness):
    def test_the_detectors_catch_an_internal_error_and_a_handler_failure(self):
        # Negative control for every check below: a real server fault is visible.
        with mock.patch.object(
            type(self.store.for_viewers(["alice"])), "search",
            side_effect=RuntimeError("boom in " + str(self.directory)),
        ):
            response = self.exchange(self.request_line())
        self.assertEqual(response, {"ok": False, "error": "internal error"})
        with self.assertRaises(AssertionError):
            self.assertClientError(response)
        with mock.patch("dynmemory.server.handle_request", side_effect=RuntimeError("escaped")):
            self.assertIsNone(self.exchange(self.request_line()))
        self.assertTrue(wait_until(lambda: self.server.handler_failures, 2))
        self.server.handler_failures.clear()
        self.assertServing()

    def test_malformed_lines_get_an_error_and_the_connection_keeps_serving(self):
        cases = {
            b"not json\n": "invalid JSON",
            b"\n": "invalid JSON",
            b"{\"token\": \n": "invalid JSON",
            b"\xff\xfe\x00garbage\n": "invalid JSON",
            b"[" * 100000 + b"\n": "invalid JSON",
            b"{\"a\":" * 100000 + b"\n": "invalid JSON",
            b"[1, 2]\n": "a request must be a JSON object",
            b"\"search\"\n": "a request must be a JSON object",
            b"null\n": "a request must be a JSON object",
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw[:20]):
                connection = self.connect()
                self.assertClientError(self.exchange(raw, connection), expected)
                # Control on the same connection: the next good line is answered.
                self.assertIs(self.exchange(self.request_line(), connection)["ok"], True)
        self.assertEqual(self.server.handler_failures, [])
        self.assertServing()

    def test_malformed_requests_are_refused_without_internal_errors(self):
        token = self.token
        cases = [
            ({"token": token, "op": "search", "args": []}, "args must be an object"),
            ({"token": token, "op": "search", "args": "query"}, "args must be an object"),
            ({"token": token, "op": "search", "args": None}, "args must be an object"),
            ({"token": token, "op": "prune", "args": {}}, "unknown operation"),
            ({"token": token, "op": None}, "unknown operation"),
            ({"token": token, "op": 5}, "unknown operation"),
            ({"token": token, "op": ["search"]}, None),
            ({"token": token, "op": "search", "args": {"query": "x", "viewers": ["bob"]}},
             "unexpected argument: viewers"),
            ({"token": token, "op": "search", "args": {"query": "x"}, "audience": "bob"},
             "audience must be a list of tokens"),
            ({"token": token, "op": "search", "args": {"query": "x"}, "audience": {"bob": 1}},
             "audience must be a list of tokens"),
            ({"token": token, "op": "search", "args": {"query": "x"}, "audience": [5]},
             "authentication failed"),
            ({"token": token, "op": "search",
              "args": {"query": "x", "record_private_access": "yes"}},
             "record_private_access must be true or false"),
            ({"token": token, "op": "search", "args": {"query": "x", "record_private_access": 1}},
             "record_private_access must be true or false"),
            ({"token": 5, "op": "search", "args": {"query": "x"}}, "authentication failed"),
            ({"op": "search", "args": {"query": "x"}}, "authentication failed"),
        ]
        for request, expected in cases:
            with self.subTest(request={k: v for k, v in request.items() if k != "token"}):
                raw = json.dumps(request).encode() + b"\n"
                self.assertClientError(self.exchange(raw), expected)
        self.assertEqual(self.server.handler_failures, [])
        self.assertServing()

    def valid_arguments(self):
        writer = self.store.for_writer("alice")
        memory = writer.add_memory("launch friday", "fact", channel="design")
        message = writer.add_message("launch is friday", channel="design")
        return {
            "search": {"query": "launch"},
            "get_memory": {"memory_id": memory.id},
            "history": {"memory_id": memory.id},
            "sources_of": {"memory_id": memory.id},
            "who_knows": {"memory_id": memory.id},
            "get_message": {"message_id": message.id},
            "disputes": {"channel": "design", "memory_key": "launch"},
            "list_memories": {},
            "list_retained_memories": {},
            "add_message": {"content": "hello", "channel": "design"},
            "add_memory": {"content": "hello", "kind": "fact", "channel": "design",
                           "fact_subject": None, "source": "conversation"},
            "acknowledge": {"message_id": message.id, "kind": "reacted"},
            "retract_message": {"message_id": message.id},
        }

    def test_wrong_types_for_string_arguments_are_client_errors(self):
        valid = self.valid_arguments()
        bad_values = (5, 1.5, True, [], {}, ["x"], {"a": 1}, 10 ** 30, "\x00", "\x00launch")
        checked = set()
        for operation in list(READS) + list(WRITES):
            base = valid[operation]
            for name in sorted(set(READS.get(operation) or WRITES[operation]) & STRING_ARGUMENTS):
                checked.add(name)
                for value in bad_values:
                    with self.subTest(operation=operation, argument=name, value=value):
                        raw = self.request_line(operation, **dict(base, **{name: value}))
                        self.assertClientError(self.exchange(raw))
        self.assertEqual(checked, set(STRING_ARGUMENTS))
        # Control: the same operations with well-typed strings succeed
        # (retract last, since it removes the message the others use).
        order = [op for op in list(READS) + list(WRITES) if op != "retract_message"]
        for operation in order + ["retract_message"]:
            with self.subTest(control=operation):
                response = self.exchange(self.request_line(operation, **valid[operation]))
                self.assertIs(response["ok"], True, response)
        self.assertEqual(self.server.handler_failures, [])

    def test_string_arguments_cover_every_text_parameter(self):
        allowed = set().union(*READS.values(), *WRITES.values())
        self.assertLessEqual(set(STRING_ARGUMENTS), allowed)
        non_text = {"limit", "include_archived", "record_private_access",
                    "confidence", "importance", "source_message_ids"}
        self.assertEqual(allowed - set(STRING_ARGUMENTS), non_text)

    def test_request_size_limit_is_inclusive_of_the_newline(self):
        base = self.request_line()
        at_limit = base[:-2] + b" " * (MAX_REQUEST_BYTES - len(base)) + b"}\n"
        self.assertEqual(len(at_limit), MAX_REQUEST_BYTES)
        connection = self.connect()
        self.assertIs(self.exchange(at_limit, connection)["ok"], True)
        # Control: the connection stays open after a request at the limit.
        self.assertIs(self.exchange(base, connection)["ok"], True)

        over = base[:-2] + b" " * (MAX_REQUEST_BYTES - len(base) + 1) + b"}\n"
        self.assertEqual(len(over), MAX_REQUEST_BYTES + 1)
        connection = self.connect()
        self.assertClientError(self.exchange(over, connection), "request too large")
        self.assertEqual(connection.recv(1), b"")  # and the server closed it
        self.assertEqual(self.server.handler_failures, [])
        self.assertServing()

    def test_an_unterminated_last_line_is_still_answered(self):
        connection = self.connect()
        connection.sendall(self.request_line()[:-1])
        connection.shutdown(socket.SHUT_WR)
        with connection.makefile("rb") as reader:
            self.assertIs(json.loads(reader.readline())["ok"], True)


@unittest.skipUnless(hasattr(socket, "AF_UNIX"), "Unix domain sockets are not available")
class SlowClientTests(ServerHarness):
    TIMEOUT = 0.3

    def test_a_half_line_that_stalls_is_closed_after_the_idle_timeout(self):
        connection = self.connect()
        connection.sendall(self.request_line()[:20])
        started = time.monotonic()
        self.assertEqual(connection.recv(1), b"")
        elapsed = time.monotonic() - started
        self.assertGreaterEqual(elapsed, self.TIMEOUT * 0.8)
        self.assertLess(elapsed, self.TIMEOUT + 3.0)
        self.assertTrue(wait_until(self.handlers_done, 3))
        self.assertEqual(self.server.handler_failures, [])

    def test_control_a_long_timeout_keeps_the_same_stalled_client_open(self):
        patient = self.start_server(30.0, name="p.sock")
        connection = self.connect(self.directory / "p.sock", timeout=1.0)
        connection.sendall(self.request_line()[:20])
        with self.assertRaises(socket.timeout):
            connection.recv(1)  # still open after more than three short timeouts
        connection.close()
        self.assertEqual(patient.handler_failures, [])

    def test_a_client_that_sends_every_half_timeout_stays_open(self):
        connection = self.connect()
        reader = connection.makefile("rb")
        self.addCleanup(reader.close)
        for _ in range(8):  # about 4 timeouts in all
            time.sleep(self.TIMEOUT / 2)
            connection.sendall(self.request_line())
            self.assertIs(json.loads(reader.readline())["ok"], True)
        self.assertEqual(len(handler_threads()), self.baseline + 1)
        connection.close()
        self.assertTrue(wait_until(self.handlers_done, 3))

    def test_many_idle_connections_do_not_block_a_fresh_client_and_then_expire(self):
        baseline = self.baseline
        timeout = 2.0
        server = self.start_server(timeout, name="m.sock")
        path = self.directory / "m.sock"
        idle = [self.connect(path) for _ in range(64)]
        # Control: all 64 are accepted and each holds a handler thread.
        self.assertTrue(wait_until(lambda: len(handler_threads()) >= baseline + 64, timeout * 0.8))
        started = time.monotonic()
        client = ScopeSpoolClient(path, self.token, timeout=5)
        self.assertEqual(client.search("launch"), [])
        self.assertLess(time.monotonic() - started, timeout * 0.75)
        self.assertGreaterEqual(len(handler_threads()), baseline + 64)  # still held
        for connection in idle:
            self.assertEqual(connection.recv(1), b"")
        self.assertTrue(wait_until(lambda: len(handler_threads()) <= baseline + 1, 5))
        self.assertEqual(server.handler_failures, [])


@unittest.skipUnless(hasattr(socket, "AF_UNIX"), "Unix domain sockets are not available")
class DisconnectTests(ServerHarness):
    def setUp(self):
        super().setUp()
        writer = self.store.for_writer("alice")
        for index in range(100):
            writer.add_memory("launch item {} {}".format(index, "x" * 2000), "fact", channel="design")

    def test_a_client_that_leaves_mid_response_does_not_hurt_the_server(self):
        big = self.request_line("list_memories", limit=100)
        for reset in (False, True):
            with self.subTest(reset=reset):
                connection = self.connect()
                connection.sendall(big * 20)
                self.assertTrue(connection.recv(64))  # a response has started
                if reset:
                    connection.setsockopt(
                        socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0)
                    )
                connection.close()
        self.assertTrue(wait_until(self.handlers_done, 5))
        # Control: the server still answers a full-size response.
        client = ScopeSpoolClient(self.socket_path, self.token, timeout=5)
        self.assertEqual(len(client.call("list_memories", limit=100)), 100)
        self.assertEqual(self.server.handler_failures, [])

    def test_a_client_that_leaves_before_its_answer_does_not_hurt_the_server(self):
        connection = self.connect()
        connection.sendall(self.request_line())
        connection.close()
        self.assertTrue(wait_until(self.handlers_done, 5))
        self.assertServing()
        self.assertEqual(self.server.handler_failures, [])


if __name__ == "__main__":
    unittest.main()
