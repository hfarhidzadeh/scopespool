"""Verify private retention and measure its local SQLite cost.

For each seed, construct identical synthetic stores for no actor read, a
default named read, an explicitly silent read, and a private opt-in read.
Repeat the opt-in condition to check determinism. Compare exact observer
outputs for an overlapping peer, a joint audience, and a disjoint member.
Every check and the reader benefit must hold in every trial.

Separately measure a fixed file-backed workload. Run the same queries with
and without private tracking on separate databases, with WAL enabled in both.
Keep one connection open per arm and checkpoint at recorded boundaries.
Report measurements for this workload without applying release budgets.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import random
import sqlite3
import statistics
import sys
import tempfile
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Barrier
from time import perf_counter
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from dynmemory import MemoryStore  # noqa: E402
from dynmemory.store import SCHEMA_VERSION  # noqa: E402


NOW = datetime(2026, 11, 25, tzinfo=timezone.utc)
TOPICS = 8
BENCH_MEMORIES = 256
BENCH_WORKERS = 4
BENCH_SERIAL = 80
BENCH_CONCURRENT = 80
BENCH_WARMUPS = 8
BENCH_LISTS = 50
BENCH_PREVIEWS = 20
SEARCH_LIMIT = 5
CHECKS = {
    "determinism": "Repeated private arm matches exactly",
    "observer_control": "Default and explicit silence match no read",
    "ranking": "Exact rankings match across paired reads and after pruning",
    "disjoint": "Disjoint observer outputs are invariant",
    "shared_trace": "Shared metadata and prune previews and outcomes match",
    "reader_benefit": "Tracking reader retains exactly the eligible read results",
}


def timestamp(instant):
    return instant.isoformat(timespec="microseconds")


@dataclass(frozen=True)
class ObserverView:
    rankings: tuple
    active: tuple
    including_archived: tuple
    history: tuple
    direct_reads: tuple
    retained: tuple


def observe(store, topic, ids):
    views = {}
    for name, audience in (("peer", "bob"), ("joint", ("alice", "bob")), ("disjoint", "carol")):
        reader = store.for_viewers(audience)
        views[name] = ObserverView(
            rankings=tuple(tuple(reader.search(query, record_access=False))
                           for query in (topic, "schedule")),
            active=tuple(reader.list_memories()),
            including_archived=tuple(reader.list_memories(include_archived=True)),
            history=tuple(tuple(reader.history(memory_id)) for memory_id in ids),
            direct_reads=tuple(reader.get_memory(memory_id) for memory_id in ids),
            retained=tuple(reader.list_retained_memories()) if isinstance(audience, str) else (),
        )
    return views


def trial_fixture(seed):
    rng = random.Random(seed)
    topic = f"topic{rng.randrange(TOPICS)}"
    age = rng.randrange(170, 220)
    limit = rng.randrange(2, 5)
    rows = [
        (1, "team", "alice", f"{topic} launch checklist", 0.25),
        (2, "team", "bob", f"{topic} schedule review", 0.20),
        (3, "team", "bob", "schedule handoff", 0.95),
        (4, "solo", "alice", f"{topic} personal reminder", 0.30),
        (5, "other", "carol", f"{topic} operations checklist", 0.35),
        (6, "other", "carol", "schedule retained reference", 0.95),
    ]
    rng.shuffle(rows)
    return topic, age, limit, rows


def trial_arm(fixture, mode):
    topic, age, limit, rows = fixture
    ids = tuple(uuid.UUID(int=index).hex for index in range(1, len(rows) + 1))
    with MemoryStore(":memory:") as store, mock.patch.object(
        store, "_now", return_value=timestamp(NOW)
    ):
        for channel, member in (("team", "alice"), ("team", "bob"),
                                ("solo", "alice"), ("other", "carol")):
            store.join_channel(channel, member)
        for index, channel, speaker, content, importance in rows:
            with mock.patch("dynmemory.store.uuid.uuid4", return_value=uuid.UUID(int=index)):
                memory = store.add_memory(content, "fact", channel=channel,
                                          speaker=speaker, importance=importance)
            store._set_activity(memory.id, created_at=timestamp(NOW - timedelta(days=age)))
        store.relate(ids[0], ids[2], "supports")
        reader = store.for_viewers("alice")
        before = observe(store, topic, ids)
        options = {"default": {}, "silent": {"record_access": False},
                   "private": {"record_private_access": True}}
        results = reader.search(topic, limit=limit, **options[mode]) if mode in options else []
        after_read = observe(store, topic, ids)
        preview = store.prune(as_of=NOW)
        archived = store.prune(as_of=NOW, dry_run=False)
        after_prune = observe(store, topic, ids)
        personal = reader.list_retained_memories()
    return before, after_read, after_prune, preview, archived, results, personal


def evaluate_trial(seed):
    fixture = trial_fixture(seed)
    baseline = trial_arm(fixture, "none")
    default = trial_arm(fixture, "default")
    silent = trial_arm(fixture, "silent")
    private = trial_arm(fixture, "private")
    before, after_read, after_prune, preview, archived, results, personal = private
    eligible = {result.memory.id for result in results} & {
        candidate.memory.id for candidate in archived
    }
    eligible_fixtures = {uuid.UUID(int=index).hex for index in (1, 2, 4, 5)}
    observed_archives = {candidate.memory.id for candidate in archived}
    return {
        "determinism": private == trial_arm(fixture, "private"),
        "observer_control": (
            default[:5] == silent[:5] == baseline[:5]
            and default[5] == silent[5]
            and not (default[6] or silent[6] or baseline[6])
            and baseline[0] == baseline[1]
            and observed_archives == eligible_fixtures
        ),
        "ranking": all(
            before[audience].rankings == after_read[audience].rankings
            and after_read[audience].rankings == silent[1][audience].rankings
            and after_prune[audience].rankings == silent[2][audience].rankings
            for audience in before
        ),
        "disjoint": before["disjoint"] == after_read["disjoint"]
        and all(private[phase]["disjoint"] == silent[phase]["disjoint"]
                for phase in range(3)),
        "shared_trace": before == after_read
        and after_prune == silent[2]
        and (preview, archived) == silent[3:5]
        and results == silent[5],
        "reader_benefit": bool(eligible)
        and {entry.memory.id for entry in personal} == eligible
        and len(personal) == len(eligible)
        and all(entry.access_count == 1 and entry.last_accessed_at == timestamp(NOW)
                and entry.memory.access_count == 0 for entry in personal),
    }


def timed(call):
    start = perf_counter()
    result = call()
    return result, (perf_counter() - start) * 1000


def latency(samples):
    ordered = sorted(samples)
    return {
        "samples": len(ordered),
        "p50_ms": statistics.median(ordered),
        "p95_ms": ordered[math.ceil(0.95 * len(ordered)) - 1],
    }


def storage(path, connection):
    count, accesses = connection.execute(
        "SELECT COUNT(*), COALESCE(SUM(access_count), 0) FROM viewer_access"
    ).fetchone()
    wal = path.with_name(path.name + "-wal")
    return {
        "db_bytes": path.stat().st_size,
        "wal_bytes": wal.stat().st_size if wal.exists() else 0,
        "private_rows": count,
        "counted_accesses": accesses,
    }


def benchmark(path, *, tracking):
    with MemoryStore(path) as store, closing(sqlite3.connect(path)) as keeper, mock.patch.object(
        store, "_now", return_value=timestamp(NOW)
    ) as clock:
        mode = keeper.execute("PRAGMA journal_mode = WAL").fetchone()[0]
        if mode != "wal":
            raise RuntimeError(f"WAL mode unavailable for temporary fixture: {mode}")
        readers = []
        for member in range(BENCH_WORKERS):
            name = f"reader{member}"
            store.join_channel("bench", name)
            readers.append(store.for_viewers(name))
        for index in range(BENCH_MEMORIES):
            importance = 0.95 if index % 7 == 0 else 0.25
            with mock.patch("dynmemory.store.uuid.uuid4", return_value=uuid.UUID(int=index + 1)):
                memory = store.add_memory(f"topic{index % TOPICS} note {index}", "fact",
                                          speaker="reader0", channel="bench", importance=importance)
            store._set_activity(memory.id, created_at=timestamp(NOW - timedelta(days=180)))

        def read(reader, index):
            return reader.search(f"topic{index % TOPICS}", limit=SEARCH_LIMIT,
                                 record_private_access=tracking)

        keeper.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        initial = storage(path, keeper)
        for index in range(BENCH_WARMUPS):
            read(readers[0], index)
        serial = [timed(lambda: read(readers[0], index))[1] for index in range(BENCH_SERIAL)]
        after_serial = storage(path, keeper)

        barrier = Barrier(BENCH_WORKERS)

        def worker(reader):
            barrier.wait(timeout=10)
            return [timed(lambda: read(reader, index))[1]
                    for index in range(BENCH_CONCURRENT // BENCH_WORKERS)]

        with ThreadPoolExecutor(max_workers=BENCH_WORKERS) as pool:
            start = perf_counter()
            samples = list(pool.map(worker, readers))
            concurrent_ops_per_second = BENCH_CONCURRENT / (perf_counter() - start)
        concurrent = [sample for group in samples for sample in group]
        after_concurrent = storage(path, keeper)
        keeper.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        checkpointed = storage(path, keeper)

        prune_preview = [timed(lambda: store.prune(as_of=NOW))[1]
                         for _ in range(BENCH_PREVIEWS)]
        archived, prune_apply_ms = timed(lambda: store.prune(as_of=NOW, dry_run=False))
        retained_list = [timed(readers[0].list_retained_memories)[1] for _ in range(BENCH_LISTS)]
        available = len(readers[0].list_retained_memories())

        clock.return_value = timestamp(NOW + timedelta(days=91))
        retained_after_expiry = len(readers[0].list_retained_memories())
        before_cleanup = storage(path, keeper)
        _, cleanup_ms = timed(lambda: store.prune(as_of=NOW, dry_run=False))
        after_cleanup = storage(path, keeper)
        expected_accesses = (BENCH_WARMUPS + BENCH_SERIAL + BENCH_CONCURRENT) * SEARCH_LIMIT
        if tracking and (after_concurrent["counted_accesses"] != expected_accesses or not available):
            raise RuntimeError("The benchmark did not record the expected private activity")
        if not tracking and (after_concurrent["private_rows"] or available):
            raise RuntimeError("The silent benchmark unexpectedly recorded private activity")
        if retained_after_expiry or after_cleanup["private_rows"]:
            raise RuntimeError("Expired activity remained visible or survived cleanup")
        return {
            "serial": latency(serial),
            "concurrent": latency(concurrent),
            "concurrent_ops_per_second": concurrent_ops_per_second,
            "retained_list": latency(retained_list),
            "prune_preview": latency(prune_preview),
            "prune_apply_ms": prune_apply_ms,
            "archived": len(archived),
            "retained_before_expiry": available,
            "retained_after_expiry": retained_after_expiry,
            "cleanup_ms": cleanup_ms,
            "storage": {
                "initial": initial, "after_serial": after_serial,
                "after_concurrent": after_concurrent, "checkpointed": checkpointed,
                "before_cleanup": before_cleanup, "after_cleanup": after_cleanup,
            },
        }


def render(report):
    total = report["trial_count"]
    silent, tracking = (report["benchmark"][arm] for arm in ("silent", "private"))
    lines = [
        "# Private retention verification",
        "",
        f"**Verification {'passed' if report['passed'] else 'failed'}.** Schema {report['schema']}. "
        f"{total} seeds compare no read, named default, explicit silence, and private tracking. "
        "Each seed varies the topic, fixture order, age, and actor search limit. "
        "The private arm is repeated for determinism.",
        "",
        "The actor is Alice, with a private channel and a shared channel. The observers are "
        "Bob in her shared channel, Alice and Bob as a joint audience, and Carol in a disjoint "
        "channel. The exact comparison includes rankings, scores, links, shared access fields, "
        "direct reads, history, active and archived lists, the observers' personal lists where "
        "available, and shared prune previews and outcomes.",
        "",
        "| Check | Passed | Required |",
        "| --- | ---: | ---: |",
    ]
    lines.extend(f"| {label} | {total - len(report['failures'][name])}/{total} | {total}/{total} |"
                 for name, label in CHECKS.items())
    lines += [
        "",
        "## Local SQLite measurements",
        "",
        f"Each arm uses a separate temporary WAL database on the same machine with {BENCH_MEMORIES} "
        f"synthetic memories, {TOPICS} topics, four named members, and a search limit of {SEARCH_LIMIT}. "
        "Silent runs first. Timing includes each API call's transaction and SQLite connection. "
        "Concurrent throughput includes starting four workers. Applied pruning is timed once per arm.",
        "",
        "| Measure | Silent | Private |",
        "| --- | ---: | ---: |",
    ]
    for name, title in (("serial", "Serial search"), ("concurrent", "Concurrent search"),
                        ("retained_list", "Personal list"), ("prune_preview", "Prune preview")):
        status = [f"{arm[name]['p50_ms']:.3f} / {arm[name]['p95_ms']:.3f} ms"
                  for arm in (silent, tracking)]
        lines.append(f"| {title} p50 / p95 | {status[0]} | {status[1]} |")
    for name, title in (("concurrent_ops_per_second", "Concurrent search calls/s"),
                        ("prune_apply_ms", "Applied prune, ms"),
                        ("cleanup_ms", "Expiry cleanup, ms")):
        lines.append(f"| {title} | {silent[name]:.3f} | {tracking[name]:.3f} |")
    for name, title in (("archived", "Shared memories archived"),
                        ("retained_before_expiry", "Personal results before expiry"),
                        ("retained_after_expiry", "Personal results after expiry")):
        lines.append(f"| {title} | {silent[name]} | {tracking[name]} |")
    lines += [
        "",
        "## Storage",
        "",
        "| Stage | Silent DB / WAL bytes / rows | Private DB / WAL bytes / rows |",
        "| --- | ---: | ---: |",
    ]
    for stage in silent["storage"]:
        sizes = [" / ".join(str(arm["storage"][stage][k])
                           for k in ("db_bytes", "wal_bytes", "private_rows"))
                 for arm in (silent, tracking)]
        lines.append(f"| {stage.replace('_', ' ')} | {sizes[0]} | {sizes[1]} |")
    lines += [
        "",
        f"Python {report['python']}, SQLite {report['sqlite']}, {report['platform']}. "
        f"Store source SHA-256 `{report['store_sha256']}`.",
        "",
        "The local timings describe one small corpus and one machine. The private personal list "
        "contains entries and the silent list is empty. WAL measurements reflect write volume "
        "between the checkpoint boundaries. Expiry removes rows without compacting the database. "
        "This fixture verifies visible API results. Server integration, observation of timing, "
        "large workloads, and release performance budgets remain separate work.",
        "",
        "Reproduce into temporary report files with "
        "`python -I experiments/private_retention_verification.py --output /tmp/private_retention_verification`.",
        "",
    ]
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--trials", type=int, default=500)
    parser.add_argument("--output", type=Path, default=ROOT / "experiments" / "results" /
                        "private_retention_verification")
    args = parser.parse_args(argv)
    if args.trials < 1:
        parser.error("--trials must be positive")
    source = ROOT / "src" / "dynmemory" / "store.py"
    store_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    failures = {name: [] for name in CHECKS}
    for seed in range(args.trials):
        for name, passed in evaluate_trial(seed).items():
            if not passed:
                failures[name].append(seed)
    with tempfile.TemporaryDirectory(prefix="scopespool-private-retention-") as directory:
        measurements = {arm: benchmark(Path(directory) / (arm + ".sqlite3"),
                                       tracking=(arm == "private"))
                        for arm in ("silent", "private")}
    if measurements["silent"]["archived"] != measurements["private"]["archived"]:
        raise RuntimeError("Benchmarks produced different numbers of shared prune candidates")
    if hashlib.sha256(source.read_bytes()).hexdigest() != store_hash:
        raise RuntimeError("Store code changed during verification")
    report = {
        "trial_count": args.trials, "passed": not any(failures.values()), "failures": failures,
        "schema": SCHEMA_VERSION, "python": platform.python_version(), "sqlite": sqlite3.sqlite_version,
        "platform": platform.platform(), "cpu_count": os.cpu_count(), "store_sha256": store_hash,
        "benchmark_config": {
            "memories": BENCH_MEMORIES, "topics": TOPICS, "search_limit": SEARCH_LIMIT,
            "workers": BENCH_WORKERS, "warmups": BENCH_WARMUPS, "serial": BENCH_SERIAL,
            "concurrent": BENCH_CONCURRENT, "lists": BENCH_LISTS, "prune_previews": BENCH_PREVIEWS,
            "arm_order": ["silent", "private"], "journal_mode": "wal",
        },
        "benchmark": measurements,
    }
    text = render(report)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.with_suffix(".json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    args.output.with_suffix(".md").write_text(text, encoding="utf-8")
    print(text)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
