"""Measure private retention over matched, repeated local SQLite workloads."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import sqlite3
import statistics
import sys
import tempfile
import uuid
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import timedelta
from pathlib import Path
from threading import Barrier
from time import perf_counter
from unittest import mock

# Make the adjacent runner importable even with Python's isolated mode.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from private_retention_verification import (  # noqa: E402
    NOW, ROOT, SCHEMA_VERSION, MemoryStore, latency, storage, timed, timestamp,
)


SIZES = ((256, 2), (1024, 4), (4096, 8))
REPETITIONS = 4
TOPICS = 32
LIMIT = 5
WARMUP = 4
SERIAL = 24
MIXED_BEFORE = 6
MIXED_AFTER = 3
PREVIEWS = 2
LIST_SAMPLES = 12
PERSONAL_LIMIT = LIMIT * (WARMUP + SERIAL + MIXED_BEFORE + MIXED_AFTER)

# Provisional flags selected before observing the pilot. Ratios compare the
# private arm to the silent arm in the same repetition; all raw runs remain.
BUDGETS = {
    "serial_p95_ratio_max": 1.30,
    "mixed_p95_ratio_max": 1.35,
    "mixed_throughput_ratio_min": 0.80,
    "checkpointed_bytes_per_row_max": 1024.0,
    "cleanup_ms_max": 50.0,
}


def seed_database(path: Path, memories: int, readers: int) -> None:
    with MemoryStore(path) as store, mock.patch.object(store, "_now", return_value=timestamp(NOW)):
        for i in range(readers):
            store.join_channel("bench", f"reader{i}")
        store.join_channel("bench", "peer")
        store.join_channel("other", "outsider")
        for i in range(memories):
            outside = i % 13 == 0
            with mock.patch("dynmemory.store.uuid.uuid4", return_value=uuid.UUID(int=i + 1)):
                memory = store.add_memory(
                    f"topic{i % TOPICS} project note {i}", "fact",
                    speaker="outsider" if outside else "reader0",
                    channel="other" if outside else "bench",
                    importance=0.95 if i % 7 == 0 else 0.25,
                )
            store._set_activity(memory.id, created_at=timestamp(NOW - timedelta(days=180)))


def copy_database(template: Path, path: Path) -> None:
    with closing(sqlite3.connect(template)) as source, closing(sqlite3.connect(path)) as dest:
        source.backup(dest)


def measure(call):
    """Keep one sample for each attempt, including lock errors and their wait."""
    start = perf_counter()
    try:
        result = call()
    except sqlite3.OperationalError as exc:
        if str(exc) not in ("database is locked", "database table is locked"):
            raise
        return None, (perf_counter() - start) * 1000, str(exc)
    return result, (perf_counter() - start) * 1000, None


def summarize_attempts(attempts):
    durations = [duration for _, duration, error in attempts if error is None]
    failures = [duration for _, duration, error in attempts if error is not None]
    return {
        "attempts": len(attempts), "successes": len(durations), "lock_errors": len(failures),
        "success_latency": latency(durations) if durations else None,
        "lock_wait": latency(failures) if failures else None,
    }


def read_calls(reader, queries, private):
    return [measure(lambda: reader.search(query, limit=LIMIT, record_private_access=private))
            for query in queries]


def mixed_calls(store, readers, queries, private):
    barrier = Barrier(len(readers) + 1, timeout=30)

    def reader_work(index):
        barrier.wait()
        return read_calls(readers[index], queries[index], private)

    def prune_work():
        barrier.wait()
        return [measure(lambda: store.prune(as_of=NOW)) for _ in range(PREVIEWS)]

    with ThreadPoolExecutor(max_workers=len(readers) + 1) as pool:
        start = perf_counter()
        future_reads = [pool.submit(reader_work, index) for index in range(len(readers))]
        future_prune = pool.submit(prune_work)
        reads = [future.result() for future in future_reads]
        previews = future_prune.result()
        elapsed = perf_counter() - start
    return reads, previews, elapsed


def scheduled_queries(offset, count, reader=0):
    return [f"topic{(offset + 7 * step + 3 * reader) % TOPICS}" for step in range(count)]


def observe(store):
    """Small canaries for both audience relationships during the scale run."""
    return {
        label: [reader.search(f"topic{topic}", limit=LIMIT, record_access=False)
                for topic in (0, 8, 16, 24)]
        for label, reader in (("peer", store.for_viewers("peer")),
                              ("shared", store.for_viewers(("reader0", "peer"))),
                              ("disjoint", store.for_viewers("outsider")))
    }


def checkpoint(connection):
    busy, _, _ = connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
    if busy:
        raise RuntimeError("Benchmark checkpoint could not complete")


def arm(path: Path, workers: int, private: bool, repeat: int):
    with MemoryStore(path) as store, closing(sqlite3.connect(path)) as keeper, mock.patch.object(
        store, "_now", return_value=timestamp(NOW)
    ) as clock:
        if keeper.execute("PRAGMA journal_mode = WAL").fetchone()[0] != "wal":
            raise RuntimeError("WAL mode not available for benchmark")
        readers = [store.for_viewers(f"reader{i}") for i in range(workers)]
        checkpoint(keeper)
        initial = storage(path, keeper)
        observer_before = observe(store)

        offset = repeat * 5
        warmup = read_calls(readers[0], scheduled_queries(offset, WARMUP), private)
        serial = read_calls(readers[0], scheduled_queries(offset + WARMUP, SERIAL), private)
        mixed_before, previews_before, elapsed_before = mixed_calls(
            store, readers, [scheduled_queries(offset + 17, MIXED_BEFORE, i)
                             for i in range(workers)], private
        )
        observer_after_reads = observe(store)
        archived, applied_ms = timed(lambda: store.prune(as_of=NOW, dry_run=False))
        observer_after_prune = observe(store)
        mixed_after, previews_after, elapsed_after = mixed_calls(
            store, readers, [scheduled_queries(offset + 23, MIXED_AFTER, i)
                             for i in range(workers)], private
        )

        before_checkpoint = storage(path, keeper)
        checkpoint(keeper)
        checkpointed = storage(path, keeper)
        archived_ids = {candidate.memory.id for candidate in archived}
        calls_by_reader = [before + after for before, after in zip(mixed_before, mixed_after)]
        calls_by_reader[0] = warmup + serial + calls_by_reader[0]
        counts = [Counter(hit.memory.id for hits, _, error in calls if error is None for hit in hits)
                  for calls in calls_by_reader]
        expected_retained = [{key: n for key, n in count.items() if key in archived_ids}
                             for count in counts]
        personal_samples = [timed(lambda: readers[i % workers].list_retained_memories(limit=PERSONAL_LIMIT))
                            for i in range(LIST_SAMPLES)]
        personal = [reader.list_retained_memories(limit=PERSONAL_LIMIT) for reader in readers]
        retention_ok = all(
            {entry.memory.id: entry.access_count for entry in retained}
            == (expected if private else {})
            for retained, expected in zip(personal, expected_retained)
        )
        private_rows = sum(len(count) for count in counts) if private else 0
        private_accesses = sum(sum(count.values()) for count in counts) if private else 0

        clock.return_value = timestamp(NOW + timedelta(days=91))
        visible_after_expiry = sum(
            len(reader.list_retained_memories(limit=PERSONAL_LIMIT)) for reader in readers
        )
        _, cleanup_ms = timed(lambda: store.prune(as_of=NOW, dry_run=False))
        after_cleanup = storage(path, keeper)
        mixed_samples = [call for reads in mixed_before + mixed_after for call in reads]
        previews = previews_before + previews_after
        mixed = summarize_attempts(mixed_samples)
        measurements = {
            "warmup": summarize_attempts(warmup),
            "serial": summarize_attempts(serial),
            "mixed": mixed,
            "mixed_successes_per_second": mixed["successes"] / (elapsed_before + elapsed_after),
            "prune_preview": summarize_attempts(previews),
            "applied_prune_ms": applied_ms,
            "personal_list": latency([duration for _, duration in personal_samples]),
            "cleanup_ms": cleanup_ms,
            "archived": len(archived),
            "eligible_personal_results": sum(len(items) for items in expected_retained),
            "personal_results": sum(len(items) for items in personal),
            "personal_results_after_expiry": visible_after_expiry,
            "storage": {
                "initial": initial,
                "before_checkpoint": before_checkpoint,
                "checkpointed": checkpointed,
                "after_cleanup": after_cleanup,
            },
        }
        checks = {
            "observer_rankings_unchanged_by_reads": observer_before == observer_after_reads,
            "retention_matches_reader_accesses": retention_ok and (
                not private or all(expected_retained)
            ),
            "shared_access_counters_unmodified": all(
                entry.memory.access_count == 0 and entry.memory.last_accessed_at is None
                for items in personal for entry in items
            ),
            "private_storage_accounting": (
                checkpointed["private_rows"], checkpointed["counted_accesses"]
            ) == (private_rows, private_accesses),
            "expiry_and_cleanup": visible_after_expiry == 0 and after_cleanup["private_rows"] == 0,
        }
        comparable = (
            [[hits for hits, _, _ in calls] for calls in calls_by_reader],
            [candidates for candidates, _, _ in previews], archived,
            observer_before, observer_after_prune,
        )
    return measurements, checks, comparable


def compare(one, other):
    added_bytes = (
        other["storage"]["checkpointed"]["db_bytes"]
        - other["storage"]["initial"]["db_bytes"]
        - one["storage"]["checkpointed"]["db_bytes"]
        + one["storage"]["initial"]["db_bytes"]
    )
    rows = other["storage"]["checkpointed"]["private_rows"]

    def p95_ratio(metric):
        silent = one[metric]["success_latency"]
        private = other[metric]["success_latency"]
        return private["p95_ms"] / silent["p95_ms"] if silent and private else None

    metrics = {
        "serial_p95_ratio": p95_ratio("serial"),
        "mixed_p95_ratio": p95_ratio("mixed"),
        "mixed_throughput_ratio": (
            other["mixed_successes_per_second"] / one["mixed_successes_per_second"]
            if one["mixed_successes_per_second"] else None
        ),
        "checkpointed_db_added_bytes": added_bytes,
        "checkpointed_added_bytes_per_row": added_bytes / rows if rows else None,
        "private_cleanup_ms": other["cleanup_ms"],
    }
    flags = {
        "serial_p95": metrics["serial_p95_ratio"] is not None
        and metrics["serial_p95_ratio"] <= BUDGETS["serial_p95_ratio_max"],
        "mixed_p95": metrics["mixed_p95_ratio"] is not None
        and metrics["mixed_p95_ratio"] <= BUDGETS["mixed_p95_ratio_max"],
        "mixed_throughput": metrics["mixed_throughput_ratio"] is not None
        and metrics["mixed_throughput_ratio"] >= BUDGETS["mixed_throughput_ratio_min"],
        "checkpointed_bytes_per_row": rows > 0 and (
            metrics["checkpointed_added_bytes_per_row"] <= BUDGETS["checkpointed_bytes_per_row_max"]
        ),
        "cleanup": metrics["private_cleanup_ms"] <= BUDGETS["cleanup_ms_max"],
    }
    return metrics, flags


def compare_outputs(silent, private):
    search = [(left, right) for left_calls, right_calls in zip(silent[0], private[0])
              for left, right in zip(left_calls, right_calls)]
    previews = list(zip(silent[1], private[1]))
    compared = [(left, right) for left, right in search + previews
                if left is not None and right is not None]
    return {
        "all_successful_pairs_equal": all(left == right for left, right in compared)
        and silent[2:] == private[2:],
        "compared_attempts": len(compared),
        "unpaired_attempts": len(search) + len(previews) - len(compared),
    }


def run(directory, sizes, repetitions):
    pairs = []
    for memories, workers in sizes:
        template = directory / "template.db"
        seed_database(template, memories, workers)
        for repeat in range(repetitions):
            order = ("silent", "private") if repeat % 2 == 0 else ("private", "silent")
            measures, checks, comparables = {}, {}, {}
            for mode in order:
                path = directory / f"{mode}.db"
                copy_database(template, path)
                measures[mode], checks[mode], comparables[mode] = arm(
                    path, workers, mode == "private", repeat
                )
                path.unlink()
            metrics, budgets = compare(measures["silent"], measures["private"])
            pairs.append({
                "memories": memories, "readers": workers, "repeat": repeat + 1,
                "arm_order": list(order), "measurements": measures,
                "checks": checks,
                "paired_comparison": compare_outputs(comparables["silent"], comparables["private"]),
                "all_calls_completed": all(
                    arm[metric]["lock_errors"] == 0 for arm in measures.values()
                    for metric in ("warmup", "serial", "mixed", "prune_preview")
                ),
                "deltas": metrics, "budget_flags": budgets,
            })
            print(f"{memories} memories, pair {repeat + 1}/{repetitions} complete", file=sys.stderr)
        template.unlink()
    return pairs


def render(report):
    pairs = report["pairs"]

    def number(value, places=2):
        return f"{value:.{places}f}" if value is not None else "n/a"

    lines = [
        "# Private retention scale pilot",
        "",
        f"**Behavior checks {'passed' if report['correctness_passed'] else 'failed'} in "
        f"{report['correct_pairs']}/{len(pairs)} paired repetitions.** "
        "Silent and private arms compared exact search results, preview and applied prune "
        "results, and observer rankings for an overlapping peer, a joint audience, and a "
        "disjoint viewer. Each private arm checked the expected retained entries, private "
        "row counts, and expiry cleanup. Search and preview comparisons include "
        "matched calls that completed in both modes.",
        "",
        f"**All calls completed in {report['available_pairs']}/{len(pairs)} pairs.** "
        "The initial full run aborted on a SQLite lock error during a private search "
        "in the 4,096-memory, eight-reader fixture. The eight smaller pairs finished "
        "before the abort, but the earlier runner emitted results only after the full "
        "run. This rerun records lock errors and failed wait times without retries.",
        "",
        "## Fixed workload",
        "",
        f"Each size starts from a shared synthetic fixture copied into independent WAL databases. "
        f"Mode order alternates across repetitions. Each pair uses the same queries in both modes. Each arm runs "
        f"{WARMUP} warmup and {SERIAL} serial searches. Before and after one applied prune, "
        f"each reader makes {MIXED_BEFORE} and {MIXED_AFTER} concurrent searches, respectively, "
        f"alongside {PREVIEWS} prune previews per phase. The personal list receives {LIST_SAMPLES} "
        "timed reads. Cleanup runs with the private access clock advanced 91 days.",
        "",
        "The local provisional flags allow private/silent p95 ratios up to 1.30 in serial "
        "and 1.35 in the mixed phase, throughput at least 0.80 of silent, at most 1,024 "
        "added checkpointed bytes per private row, and at most 50 ms for private cleanup. "
        "These flags identify workloads to investigate before planning a release.",
        "",
        "## Results by workload",
        "",
        "Values are medians across repetitions. Each cell lists silent / private values. "
        "Search and preview p50/p95 cover successful calls. Throughput counts successful "
        "searches over all elapsed time, including time spent waiting on failed calls.",
        "",
        "| Memories / readers | Serial p50 / p95 (ms) | Mixed p50 / p95 (ms) | Successful mixed searches/s | Prune preview p95 / apply (ms) | Personal list p95 (ms) | Cleanup (ms) |",
        "| --- | --- | --- | ---: | --- | ---: | ---: |",
    ]
    for size in report["config"]["sizes"]:
        group = [pair for pair in pairs if pair["memories"] == size["memories"]]

        def med(arm_name, *keys):
            values = []
            for pair in group:
                value = pair["measurements"][arm_name]
                for key in keys:
                    if value is not None:
                        value = value[key]
                if value is not None:
                    values.append(value)
            return statistics.median(values) if values else None

        def both(*keys):
            return " / ".join(number(med(mode, *keys)) for mode in ("silent", "private"))

        def percentiles(metric):
            return " / ".join(
                f"{number(med(mode, metric, 'success_latency', 'p50_ms'))}, "
                f"{number(med(mode, metric, 'success_latency', 'p95_ms'))}"
                for mode in ("silent", "private")
            )

        prune = " / ".join(f"{number(med(mode, 'prune_preview', 'success_latency', 'p95_ms'))}, "
                           f"{number(med(mode, 'applied_prune_ms'))}"
                           for mode in ("silent", "private"))
        lines.append(f"| {size['memories']:,} / {size['readers']} | {percentiles('serial')} | "
                     f"{percentiles('mixed')} | {both('mixed_successes_per_second')} | {prune} | "
                     f"{both('personal_list', 'p95_ms')} | {both('cleanup_ms')} |")
    lines += [
        "",
        "## Availability",
        "",
        "| Memories | Pair | Mixed searches completed, silent / private | Private mixed lock wait p95 (ms) | Unpaired search or preview attempts |",
        "| ---: | ---: | ---: | ---: | ---: |",
    ]
    for pair in pairs:
        modes = pair["measurements"]
        completed = " / ".join(f"{modes[mode]['mixed']['successes']}/{modes[mode]['mixed']['attempts']}"
                               for mode in ("silent", "private"))
        waits = modes["private"]["mixed"]["lock_wait"]
        wait_p95 = number(waits["p95_ms"]) if waits else "n/a"
        lines.append(f"| {pair['memories']:,} | {pair['repeat']} | {completed} | {wait_p95} | "
                     f"{pair['paired_comparison']['unpaired_attempts']} |")
    lines += [
        "",
        "## Paired ratios and storage",
        "",
        "| Memories | Pair, first arm | Serial p95 ratio | Mixed p95 ratio | Throughput ratio | WAL bytes, silent / private | Added DB bytes / private rows | Added bytes/row | Archived, silent / private | Personal results before / after expiry | Flags missed |",
        "| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for pair in pairs:
        m = pair["measurements"]
        private = m["private"]
        delta = pair["deltas"]
        wal = " / ".join(f"{m[mode]['storage']['before_checkpoint']['wal_bytes']:,}"
                         for mode in ("silent", "private"))
        rows = private["storage"]["checkpointed"]["private_rows"]
        ratio = delta["checkpointed_added_bytes_per_row"]
        bytes_per_row = f"{ratio:.1f}" if ratio is not None else "n/a"
        missed = ", ".join(key.replace("_", " ") for key, passed in pair["budget_flags"].items()
                           if not passed) or "None"
        lines.append(
            f"| {pair['memories']:,} | {pair['repeat']}, {pair['arm_order'][0]} | "
            f"{number(delta['serial_p95_ratio'], 3)} | {number(delta['mixed_p95_ratio'], 3)} | "
            f"{number(delta['mixed_throughput_ratio'], 3)} | {wal} | "
            f"{delta['checkpointed_db_added_bytes']:,} / {rows:,} | {bytes_per_row} | "
            f"{m['silent']['archived']:,} / {private['archived']:,} | "
            f"{private['personal_results']} / {private['personal_results_after_expiry']} | {missed} |"
        )
    misses = sum(not all(pair["budget_flags"].values()) for pair in pairs)
    lines += [
        "",
        f"{misses}/{len(pairs)} repetitions missed at least one provisional flag. "
        "The JSON report preserves each arm's measurements and individual checks.",
        "",
        f"Python {report['python']}, SQLite {report['sqlite']}, {report['platform']}. "
        f"Schema {report['schema']}, store source SHA-256 `{report['store_sha256']}`. "
        f"Elapsed time {report['elapsed_seconds']:.1f} s.",
        "",
        "The fixture is synthetic and measures one host and runtime. Mixed throughput includes "
        "starting workers and waiting for the prune previews. WAL bytes are file sizes before "
        "the explicit checkpoint, and checkpointed DB growth includes index and page allocation. "
        "Expiry cleanup deletes rows while SQLite retains allocated pages for reuse.",
        "",
        "Re-run with `python3 -I experiments/private_retention_scale.py --output /tmp/private_retention_scale`.",
        "",
    ]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path,
                        default=ROOT / "experiments/results/private_retention_scale")
    parser.add_argument("--smoke", action="store_true",
                        help="Use a single 256-memory pair to check the runner")
    args = parser.parse_args()
    sizes = SIZES[:1] if args.smoke else SIZES
    repetitions = 1 if args.smoke else REPETITIONS
    source = ROOT / "src/dynmemory/store.py"
    store_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    start = perf_counter()
    with tempfile.TemporaryDirectory(prefix="scopespool-retention-scale-") as directory:
        pairs = run(Path(directory), sizes, repetitions)
    if hashlib.sha256(source.read_bytes()).hexdigest() != store_hash:
        raise RuntimeError("Store source changed during the benchmark")
    correct_pairs = sum(
        pair["paired_comparison"]["all_successful_pairs_equal"]
        and all(all(checks.values()) for checks in pair["checks"].values())
        for pair in pairs
    )
    available_pairs = sum(pair["all_calls_completed"] for pair in pairs)
    report = {
        "schema": SCHEMA_VERSION, "python": platform.python_version(), "sqlite": sqlite3.sqlite_version,
        "platform": platform.platform(), "cpu_count": os.cpu_count(), "store_sha256": store_hash,
        "elapsed_seconds": perf_counter() - start,
        "correctness_passed": correct_pairs == len(pairs), "correct_pairs": correct_pairs,
        "availability_passed": available_pairs == len(pairs), "available_pairs": available_pairs,
        "initial_run": {
            "completed_pairs_before_abort": 8, "error": "database is locked",
            "during": "first mixed private search phase at 4096 memories and 8 readers",
            "smaller_pair_measurements_emitted": False,
        },
        "config": {
            "sizes": [{"memories": memories, "readers": readers} for memories, readers in sizes],
            "repetitions": repetitions, "topics": TOPICS, "search_limit": LIMIT,
            "warmup": WARMUP, "serial": SERIAL, "mixed_before": MIXED_BEFORE,
            "mixed_after": MIXED_AFTER, "previews_per_phase": PREVIEWS,
            "retained_list_samples": LIST_SAMPLES, "retained_list_limit": PERSONAL_LIMIT,
            "journal_mode": "wal",
            "provisional_budgets": BUDGETS,
        },
        "pairs": pairs,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    markdown = render(report)
    args.output.with_suffix(".json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    args.output.with_suffix(".md").write_text(markdown, encoding="utf-8")
    print(markdown)
    return 0 if report["correctness_passed"] and report["availability_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
