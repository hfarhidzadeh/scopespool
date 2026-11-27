"""Measure authenticated private retention through the production Unix-socket client and server.

Acceptance gate, fixed on 2026-11-26 before any recorded run. Each pair runs a
silent arm and a private arm on copies of the same fixture, through a separate
``scopespool serve`` process, signed tokens and ``ScopeSpoolClient``. Each
criterion must hold in every pair:

  (a) No failed requests: every warmup, serial, concurrent, observer and
      personal-list request and every concurrent prune preview completed in both
      arms, with no client-visible error (a SQLite lock surfaces as one).
  (b) Shared results match: the silent and private arms returned identical
      search results in every phase, identical observer search probes (the
      overlapping peer, the joint audience with reader0, the disjoint outsider),
      identical prune previews and an identical applied prune; and in each arm
      the observer search probes were unchanged by the readers' searches and
      non-empty.
  (c) A retained result for every private reader: in the private arm, every
      reader's personal list after the prune equals the archived memories that
      reader's own searches returned, with their counts, and is non-empty; in
      the silent arm every personal list is empty.
  (d) No cross-member attribution: the peer's and the outsider's personal lists
      are empty before the reads, after the reads and after the prune, in both
      arms; after the arm, the database holds private rows only for readers who
      made private searches (none at all in the silent arm).

Verdict: "pass" if (a) to (d) hold in every pair; otherwise "fail", naming the
failing criteria and the first failing size and pair. Latency and throughput
are reported and are not part of the gate.

Validation, fixed before running: ``--fault wrong-member`` makes the server
process record each private search for ``peer`` instead of the token's member.
Criterion (d) must then fail in every pair, or this benchmark cannot detect the
attribution error it is for. A fault run exits 0 only when the fault was
detected.

The store, server, auth, CLI and benchmark sources are hashed before the run and
checked after every pair; the run stops if any of them changed.

Smoke check: ``--smoke`` (one 256-memory pair). Write recorded runs to a new
path, for example
``python3 -I experiments/private_retention_socket.py --output "$(mktemp -d)/private_retention_socket"``.

Measurement aid, added 2026-11-27 and not part of the gate above:
``--persistent-client`` sends each member's calls over one kept-open connection
(a benchmark-local client speaking the same protocol) instead of
``ScopeSpoolClient``'s connection per call. It exists to measure what
connection reuse would save; the default run, its workload and its gate are
unchanged, and runs with this option are not comparable to recorded runs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import select
import signal
import socket
import sqlite3
import subprocess
import sys
import tempfile
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing, contextmanager
from pathlib import Path
from threading import Barrier, Lock
from time import perf_counter
from typing import NamedTuple, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
from private_retention_scale import (  # noqa: E402
    LIMIT, NOW, PREVIEWS, ROOT, SERIAL, WARMUP, MemoryStore, copy_database, latency,
    scheduled_queries, seed_database,
)
from private_retention_scale import REPETITIONS as SCALE_REPETITIONS  # noqa: E402
from private_retention_scale import SIZES as SCALE_SIZES  # noqa: E402
from dynmemory.auth import TokenAuthority  # noqa: E402
from dynmemory.server import MAX_REQUEST_BYTES, RemoteError, ScopeSpoolClient  # noqa: E402

TITLE = "Private retention over the Unix socket"
SIZES = SCALE_SIZES
REPETITIONS = SCALE_REPETITIONS
CONCURRENT_PER_READER = 12
PERSONAL_ROUNDS = 6
CLIENT_TIMEOUT_SECONDS = 30.0
FAULTS = ("wrong-member",)
WRONG_MEMBER = "peer"
GATE_CRITERIA = {
    "a_no_failed_requests": "every request and concurrent prune preview completed in both arms",
    "b_results_match": "identical searches, observer probes, previews and applied prune between arms",
    "c_retained_for_every_reader": "each private reader's list equals its own archived results; "
                                   "silent lists empty",
    "d_no_cross_member_attribution": "peer and outsider lists empty; private rows only for "
                                     "readers who searched privately",
}
SOURCES = ("src/dynmemory/store.py", "src/dynmemory/server.py", "src/dynmemory/auth.py",
           "src/dynmemory/cli.py", "experiments/private_retention_socket.py",
           "experiments/private_retention_scale.py", "experiments/private_retention_verification.py")

# Runs inside the server process: optionally install a fault, then serve as the CLI does.
SERVER_BOOT = """
import signal, sys
# The benchmark stops the server with SIGINT. A shell starts background jobs
# with SIGINT ignored and Python keeps it ignored, so restore the handler.
signal.signal(signal.SIGINT, signal.default_int_handler)
fault, argv = sys.argv[1], sys.argv[2:]
if fault == "wrong-member":
    from dynmemory.store import MemoryStore
    original = MemoryStore._record_private_access
    def misattributed(self, viewer_id, memory_ids, now):
        return original(self, {member!r}, memory_ids, now)
    MemoryStore._record_private_access = misattributed
elif fault != "none":
    raise SystemExit("unknown fault: " + fault)
from dynmemory.cli import main
raise SystemExit(main(argv))
""".format(member=WRONG_MEMBER)


class PersistentClient:
    """Benchmark-only: one member's calls over a single kept-open connection.

    Speaks ScopeSpoolClient's newline-delimited JSON, but opens the socket on
    the first call and keeps it. A failed exchange closes the connection, so
    the next call opens a new one; nothing is retried. A lock serialises
    callers, so a reply can never be read by the wrong call.
    """

    def __init__(self, socket_path, token, *, timeout):
        self.socket_path, self.token, self.timeout = str(socket_path), token, timeout
        self.connections_opened = 0
        self._connection = self._reader = None
        self._lock = Lock()

    def close(self):
        for resource in (self._reader, self._connection):
            if resource is not None:
                resource.close()
        self._connection = self._reader = None

    def call(self, operation, *, audience=None, **arguments):
        message = {"token": self.token, "op": operation, "args": arguments}
        if audience:
            message["audience"] = list(audience)
        with self._lock:
            try:
                if self._connection is None:
                    self._connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                    self._connection.settimeout(self.timeout)
                    self._connection.connect(self.socket_path)
                    self._reader = self._connection.makefile("rb")
                    self.connections_opened += 1
                self._connection.sendall(json.dumps(message).encode("utf-8") + b"\n")
                line = self._reader.readline(MAX_REQUEST_BYTES * 8)
                if not line.endswith(b"\n"):
                    raise ConnectionError("the server closed the connection")
            except BaseException:
                self.close()
                raise
        response = json.loads(line.decode("utf-8"))
        if not response.get("ok"):
            raise RemoteError(response.get("error", "request failed"))
        return response["result"]

    def search(self, query, **arguments):
        return self.call("search", query=query, **arguments)

    def list_retained_memories(self, *, limit=100):
        return self.call("list_retained_memories", limit=limit)


class Attempt(NamedTuple):
    result: object
    ms: float
    error: Optional[str]


def request(call, *args, **kwargs):
    start = perf_counter()
    try:
        result = call(*args, **kwargs)
    except (RemoteError, OSError, json.JSONDecodeError, sqlite3.Error) as error:
        return Attempt(None, (perf_counter() - start) * 1000, f"{type(error).__name__}: {error}")
    return Attempt(result, (perf_counter() - start) * 1000, None)


def metrics(attempts):
    successes = [sample.ms for sample in attempts if sample.error is None]
    failures = [sample for sample in attempts if sample.error is not None]
    return {
        "attempts": len(attempts), "successes": len(successes),
        "success_latency": latency(successes) if successes else None,
        "errors": dict(Counter(sample.error for sample in failures)),
        "error_latency": latency([sample.ms for sample in failures]) if failures else None,
    }


@contextmanager
def running_server(database, socket_path, secret_file, fault=None):
    # Start the same CLI entry point as an installed server. The package lives in src/.
    cmd = [sys.executable, "-EsB", "-c", SERVER_BOOT, fault or "none", "--db", str(database),
           "serve", "--socket", str(socket_path), "--secret-file", str(secret_file)]
    with subprocess.Popen(cmd, cwd=ROOT / "src", stdout=subprocess.PIPE, text=True) as process:
        try:
            ready, _, _ = select.select([process.stdout], [], [], 30)
            if not ready or not process.stdout.readline().startswith("Serving "):
                raise RuntimeError("The server did not announce a listening Unix socket")
            yield
        finally:
            if process.poll() is None:
                process.send_signal(signal.SIGINT)
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
                raise RuntimeError("The benchmark server did not shut down") from None
            if process.returncode and sys.exc_info()[0] is None:
                raise RuntimeError(f"The benchmark server exited with status {process.returncode}")


def search_probes(clients):
    peer, outsider = clients["peer"], clients["outsider"]
    return [
        request(peer.search, "topic0", limit=LIMIT),
        request(peer.search, "topic8", audience=[clients["reader0"].token], limit=LIMIT),
        request(outsider.search, "topic13", limit=LIMIT),
    ]


def list_probes(clients):
    return [request(clients["peer"].list_retained_memories),
            request(clients["outsider"].list_retained_memories)]


def private_members(database):
    with closing(sqlite3.connect(database)) as connection:
        return sorted(row[0] for row in connection.execute(
            "SELECT DISTINCT member_id FROM viewer_access"))


def arm(root, template, reader_count, private, offset, secret_file, authority, fault=None,
        persistent=False):
    database, socket_path = root / "store.db", root / "s.sock"
    copy_database(template, database)
    with closing(sqlite3.connect(database)) as setup:
        if setup.execute("PRAGMA journal_mode=WAL").fetchone()[0] != "wal":
            raise RuntimeError("WAL mode unavailable")
    names = [f"reader{i}" for i in range(reader_count)]
    client_class = PersistentClient if persistent else ScopeSpoolClient
    clients = {name: client_class(socket_path, authority.issue(name), timeout=CLIENT_TIMEOUT_SECONDS)
               for name in [*names, "peer", "outsider"]}
    options = {"record_private_access": True} if private else {}

    def searches(reader, queries):
        return [request(clients[reader].search, query, limit=LIMIT, **options) for query in queries]

    with running_server(database, socket_path, secret_file, fault), MemoryStore(database) as admin:
        before, lists_before = search_probes(clients), list_probes(clients)
        warmup = searches(names[0], scheduled_queries(offset, WARMUP))
        serial = searches(names[0], scheduled_queries(offset + WARMUP, SERIAL))
        barrier = Barrier(reader_count + 1, timeout=30)

        def worker(index):
            barrier.wait()
            return searches(names[index], scheduled_queries(offset + 17, CONCURRENT_PER_READER, index))

        def previews():
            # Prune previews need the trusted local store; they run alongside the socket reads.
            barrier.wait()
            return [request(admin.prune, as_of=NOW) for _ in range(PREVIEWS)]

        start = perf_counter()
        with ThreadPoolExecutor(reader_count + 1) as pool:
            reader_futures = [pool.submit(worker, index) for index in range(reader_count)]
            preview_future = pool.submit(previews)
            by_reader = [future.result() for future in reader_futures]
            preview_attempts = preview_future.result()
        elapsed = perf_counter() - start
        after_reads, lists_after_reads = search_probes(clients), list_probes(clients)
        archived = admin.prune(as_of=NOW, dry_run=False)
        after_prune, lists_after_prune = search_probes(clients), list_probes(clients)
        personal = [[request(clients[name].list_retained_memories, limit=1000) for name in names]
                    for _ in range(PERSONAL_ROUNDS)]
        if persistent:
            for client in clients.values():
                client.close()
    members = private_members(database)

    concurrent = [sample for samples in by_reader for sample in samples]
    observer_lists = lists_before + lists_after_reads + lists_after_prune
    series = {"warmup": warmup, "serial": serial, "concurrent": concurrent,
              "observer": before + after_reads + after_prune, "observer_lists": observer_lists,
              "prune_preview": preview_attempts,
              "personal_list": [sample for samples in personal for sample in samples]}
    measured = {name: metrics(samples) for name, samples in series.items()}
    archived_ids = {item.memory.id for item in archived}
    expected = []
    for i, samples in enumerate(by_reader):
        searches_by_member = (warmup + serial if i == 0 else []) + samples
        expected.append(Counter(hit["memory"]["id"] for sample in searches_by_member
                                if sample.error is None for hit in sample.result
                                if hit["memory"]["id"] in archived_ids))
    retention_ok = all(expected)
    for samples in personal:
        for sample, eligible in zip(samples, expected):
            if sample.error is not None:
                retention_ok = False
                continue
            observed = {row["memory"]["id"]: row["access_count"] for row in sample.result}
            retention_ok &= (observed == (eligible if private else {})
                             and len(observed) == len(sample.result)
                             and all(row["memory"]["access_count"] == 0 and row["last_accessed_at"]
                                     for row in sample.result))
    shared = {name: [sample.result for sample in series[name]]
              for name in ("warmup", "serial", "concurrent", "observer", "prune_preview")}
    shared["applied_prune"] = archived
    allowed_members = set(names) if private else set()
    checks = {
        "all_calls_completed": all(m["successes"] == m["attempts"] for m in measured.values()),
        "observer_unchanged_by_reads": [s.result for s in before] == [s.result for s in after_reads],
        "observer_probes_nonempty": all(s.error is None and s.result for s in before),
        "observer_lists_empty": all(s.error is None and s.result == [] for s in observer_lists),
        "personal_ids_and_counts_match": bool(retention_ok),
        "private_rows_only_for_searching_readers": set(members) <= allowed_members,
    }
    result = {
        "phases": measured, "concurrent_wall_seconds": elapsed,
        "concurrent_successes_per_second": measured["concurrent"]["successes"] / elapsed,
        "shared_archived": len(archived), "eligible_by_reader": [len(ids) for ids in expected],
        "retained_by_reader": [len(s.result) if s.error is None else None for s in personal[-1]],
        "private_members": members,
        "checks": checks,
    }
    if persistent:
        result["connections_by_member"] = {name: client.connections_opened
                                           for name, client in clients.items()}
    return result, shared


def source_hashes():
    return {path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in SOURCES}


def gate_criteria(pair):
    """Which acceptance criteria hold for one pair; see the module docstring."""
    silent, private = pair["arms"]["silent"], pair["arms"]["private"]
    arms = (silent, private)
    retained = private["retained_by_reader"]
    return {
        "a_no_failed_requests": all(a["checks"]["all_calls_completed"] for a in arms),
        "b_results_match": bool(pair["exact_match"]) and all(pair["exact_match"].values()) and all(
            a["checks"]["observer_unchanged_by_reads"] and a["checks"]["observer_probes_nonempty"]
            for a in arms),
        "c_retained_for_every_reader": bool(
            private["checks"]["personal_ids_and_counts_match"]
            and silent["checks"]["personal_ids_and_counts_match"]
            and len(retained) == pair["readers"]
            and all(count is not None and count > 0 for count in retained)
            and all(count == 0 for count in silent["retained_by_reader"])
        ),
        "d_no_cross_member_attribution": all(
            a["checks"]["observer_lists_empty"]
            and a["checks"]["private_rows_only_for_searching_readers"] for a in arms
        ) and silent["private_members"] == [],
    }


def acceptance_gate(pairs):
    held = {name: [] for name in GATE_CRITERIA}
    failing = {name: [] for name in GATE_CRITERIA}
    outcomes = [(pair, gate_criteria(pair)) for pair in pairs]
    for pair, criteria in outcomes:
        label = {"memories": pair["memories"], "readers": pair["readers"], "pair": pair["pair"]}
        for name, ok in criteria.items():
            (held if ok else failing)[name].append(label)
    failed = [name for name in GATE_CRITERIA if failing[name]]
    first = next(({"memories": pair["memories"], "readers": pair["readers"], "pair": pair["pair"],
                   "criteria": [name for name, ok in criteria.items() if not ok]}
                  for pair, criteria in outcomes if not all(criteria.values())), None)
    passed = bool(pairs) and not failed
    if passed:
        verdict = "pass"
    elif not pairs:
        verdict = "fail (no pairs ran)"
    else:
        verdict = "fail ({} failed; first failing: {:,} memories, pair {})".format(
            ", ".join(name.split("_", 1)[0] for name in failed), first["memories"], first["pair"])
    return {
        "verdict": verdict, "passed": passed, "pairs": len(pairs),
        "criteria": {name: {"description": GATE_CRITERIA[name], "held": len(held[name]),
                            "failing": failing[name]} for name in GATE_CRITERIA},
        "first_failure": first,
    }


def validate_fault(fault, gate):
    """The injected fault must fail criterion (d) in every pair."""
    if fault is None:
        return None
    failing = len(gate["criteria"]["d_no_cross_member_attribution"]["failing"])
    return {"fault": fault, "criterion": "d", "failed_pairs": failing, "pairs": gate["pairs"],
            "detected": gate["pairs"] > 0 and failing == gate["pairs"]}


def run(directory, sizes, repetitions, fault=None, hashes=None, persistent=False):
    secret = TokenAuthority.generate_secret()
    secret_file = directory / "signing-key"
    with os.fdopen(os.open(secret_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as out:
        out.write(secret.hex())
    authority = TokenAuthority(secret)
    pairs = []
    for memories, readers in sizes:
        template = directory / f"fixture-{memories}.db"
        seed_database(template, memories, readers)
        for repeat in range(repetitions):
            modes = ("private", "silent") if repeat % 2 else ("silent", "private")
            arms, shared = {}, {}
            for mode in modes:
                with tempfile.TemporaryDirectory(dir=directory) as arm_dir:
                    arms[mode], shared[mode] = arm(Path(arm_dir), template, readers, mode == "private",
                                                   5 * repeat, secret_file, authority, fault,
                                                   persistent)
            if hashes is not None and source_hashes() != hashes:
                raise RuntimeError("Source files changed while the benchmark was running")
            equal = {name: shared["silent"][name] == shared["private"][name] for name in shared["silent"]}
            pair = {"memories": memories, "readers": readers, "pair": repeat + 1,
                    "order": list(modes), "arms": arms, "exact_match": equal}
            pair["gate_criteria"] = gate_criteria(pair)
            pair["passed"] = all(pair["gate_criteria"].values())
            pairs.append(pair)
            print(f"{memories} memories, pair {repeat + 1}/{repetitions} complete", file=sys.stderr)
    return pairs


def render(report):
    config, gate = report["config"], report["acceptance_gate"]
    sizes = ", ".join(f"{size['memories']:,}/{size['readers']}" for size in config["sizes"])
    lines = [
        f"# {TITLE}", "",
        f"Sizes (memories/readers) {sizes}; {config['repetitions']} paired repetitions"
        + (f"; injected fault: {report['fault']}" if report["fault"] else "")
        + ("; persistent client (one connection per member, not the gated client)"
           if config.get("persistent_client") else "") + ".", "",
        f"**Acceptance gate: {gate['verdict']}.** Pre-registered in the script's docstring; "
        "each criterion must hold in every pair.", "",
        "| Criterion | Pairs held |", "| --- | ---: |",
    ]
    for name, item in gate["criteria"].items():
        lines.append(f"| ({name[0]}) {item['description']} | {item['held']}/{gate['pairs']} |")
    if report.get("validation"):
        check = report["validation"]
        lines += ["", "Fault validation: criterion (d) failed in {}/{} pairs; {}.".format(
            check["failed_pairs"], check["pairs"], "detected" if check["detected"] else "NOT detected")]
    client_text = (
        "A benchmark-local client keeps one local socket per member open for all of that "
        "member's calls" if config.get("persistent_client") else
        "The production client opens a new local socket for each call")
    lines += [
        "",
        client_text + " to a separate threaded "
        "ScopeSpool server process. Timings include connection setup, signed-token verification, "
        "JSON, store work and the decoded response. The harness seeds independent copies of a "
        "synthetic WAL database, starts the server, issues tokens, runs prune previews through the "
        "trusted local store alongside the concurrent socket reads, and applies the administrative "
        "prune outside the timed client calls.", "",
        f"Each arm runs {WARMUP} warmup and {SERIAL} serial searches, {CONCURRENT_PER_READER} "
        f"concurrent searches per reader with {PREVIEWS} prune previews, and {PERSONAL_ROUNDS} "
        f"personal-list calls per reader. Search limit {LIMIT}. The peer, joint audience and "
        "disjoint viewer are queried before the workload, after the reads, and after pruning. "
        "Arm order alternates by repetition.", "",
        "| Memories / readers | Pair | Mode | All requests OK / attempted | Serial p95 (ms) | "
        "Concurrent p95 (ms) | Successful concurrent calls/s | Preview p95 (ms) | "
        "Personal list p95 (ms) | Retained per reader |",
        "| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for pair in report["pairs"]:
        for mode in pair["order"]:
            arm_data = pair["arms"][mode]
            phases = arm_data["phases"]
            completed = sum(phase["successes"] for phase in phases.values())
            attempts = sum(phase["attempts"] for phase in phases.values())
            p95 = [f"{phases[k]['success_latency']['p95_ms']:.2f}" if phases[k]["success_latency"]
                   else "n/a" for k in ("serial", "concurrent", "prune_preview", "personal_list")]
            counts = ", ".join("n/a" if count is None else str(count)
                               for count in arm_data["retained_by_reader"])
            lines.append(f"| {pair['memories']:,} / {pair['readers']} | {pair['pair']} | {mode} | "
                         f"{completed}/{attempts} | {p95[0]} | {p95[1]} | "
                         f"{arm_data['concurrent_successes_per_second']:.2f} | {p95[2]} | {p95[3]} | "
                         f"{counts} |")
    lines.extend([
        "", "Latency percentiles summarize successful requests. Concurrent throughput divides "
        "successful searches by total wall time, including failed calls and worker startup. "
        "The JSON records client-visible errors and their latency separately. Results describe "
        "this local lexical fixture and runtime; latency and throughput are not gated.", "",
        f"Python {report['python']}, SQLite {report['sqlite']}, {report['platform']}. "
        f"Store SHA-256 `{report['source_sha256']['src/dynmemory/store.py']}`. "
        f"Server SHA-256 `{report['source_sha256']['src/dynmemory/server.py']}`. "
        f"Elapsed time {report['elapsed_seconds']:.1f} s.", "",
    ])
    return "\n".join(lines)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--output", type=Path,
                        default=ROOT / "experiments/results/private_retention_socket")
    parser.add_argument("--smoke", action="store_true", help="Run one 256-memory pair")
    parser.add_argument("--size", type=int, action="append",
                        choices=[memories for memories, _ in SIZES],
                        help="Run only this fixed size (repeatable)")
    parser.add_argument("--repetitions", type=int,
                        help="Paired repetitions per size (default {})".format(REPETITIONS))
    parser.add_argument("--fault", choices=FAULTS,
                        help="Inject a server fault to validate the gate")
    parser.add_argument("--persistent-client", action="store_true",
                        help="Send each member's calls over one connection (measurement aid; "
                             "not the gated client)")
    args = parser.parse_args(argv)
    if args.smoke and (args.size or args.repetitions is not None):
        parser.error("--smoke cannot be combined with --size or --repetitions")
    if args.repetitions is not None and args.repetitions < 1:
        parser.error("--repetitions must be at least 1")
    if args.smoke:
        args.sizes, args.repetitions = SIZES[:1], 1
    else:
        args.sizes = tuple(size for size in SIZES if not args.size or size[0] in args.size)
        args.repetitions = REPETITIONS if args.repetitions is None else args.repetitions
    return args


def build_config(sizes, repetitions, smoke=False, persistent=False):
    config = {"smoke": smoke,
              "sizes": [{"memories": memories, "readers": readers} for memories, readers in sizes],
              "repetitions": repetitions, "warmup": WARMUP, "serial": SERIAL,
              "concurrent_per_reader": CONCURRENT_PER_READER, "previews_per_phase": PREVIEWS,
              "personal_rounds": PERSONAL_ROUNDS, "search_limit": LIMIT,
              "client_timeout_s": CLIENT_TIMEOUT_SECONDS}
    if persistent:
        config["persistent_client"] = True
    return config


def main(argv=None):
    args = parse_args(argv)
    hashes = source_hashes()
    start = perf_counter()
    # Use a short private directory to fit macOS's 104-byte Unix socket path.
    with tempfile.TemporaryDirectory(prefix="ss-sock-", dir="/tmp") as directory:
        pairs = run(Path(directory), args.sizes, args.repetitions, args.fault, hashes,
                    args.persistent_client)
    if hashes != source_hashes():
        raise RuntimeError("Source files changed while the benchmark was running")
    gate = acceptance_gate(pairs)
    report = {
        "passed": gate["passed"], "acceptance_gate": gate, "fault": args.fault,
        "validation": validate_fault(args.fault, gate), "pairs": pairs,
        "config": build_config(args.sizes, args.repetitions, args.smoke, args.persistent_client),
        "source_sha256": hashes, "python": platform.python_version(), "sqlite": sqlite3.sqlite_version,
        "platform": platform.platform(), "elapsed_seconds": perf_counter() - start,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.with_suffix(".json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    markdown = render(report)
    args.output.with_suffix(".md").write_text(markdown, encoding="utf-8")
    print(markdown)
    if args.fault:
        return 0 if report["validation"]["detected"] else 1
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
