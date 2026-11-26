"""Verify the Stage C loader on EverMemBench-Dynamic's five pinned release topics.

Before running, the pass criterion is lexical all-required@10 = 1.0 over ALL
questions with at most ten R entries. Append one unique token to the original
question and to one source message from each R entry. Reset those rows before
the next question, so the rest of the topic always has its original text.

Deviation, 2026-11-26. Run 1 under the rule above failed: 117 of 2,212 eligible
questions (0.053) reached all-required@10, and the unplanted token returned no
results. Codex and an independent audit produced byte-identical reports; run 1
is kept in ``experiments/results/evermembench_control_run1_superseded/``. The
rule was unachievable with BM25, not a loader fault: one rare token appended to
the full question cannot outrank messages that match several of the question's
mid-frequency words, and BM25's length normalisation penalises the long planted
messages. In every topic the token alone returned exactly the planted messages
and covered every R entry.

New rule, fixed before run 2: plant the token as before, but query the token
alone. For each eligible question (at most ten R entries), the lexical top 10
of the token-only query must cover every R entry, so all-required@10 = 1.0 on
the token-only query; and an unplanted token must return zero results. This
checks that every planted witness, chosen from the raw intervals independently
of the loader, is stored, retrievable through the public search and maps back
to a coordinate inside its R entry. It no longer measures whether the question
text ranks the evidence; that retrieval-quality figure is run 1's 0.053.
``--rule original`` reproduces run 1's rule.

Fault check, fixed before run 2: ``--fault off-by-one`` plants each witness one
message index higher (a 0-/1-based mix-up), dropping it when that message does
not exist. A witness is the highest matching index of its entry, so the shifted
message is never in that entry; the rule must then fail.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
from concurrent.futures import ProcessPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from dynmemory.evermembench import DATASET, FILE_HASHES, REVISION, read_topic_files, topic_memories
from dynmemory.store import MemoryStore

DEPTH = 10
PREFIX = "scopespoolevermemcanary"
RULES = ("token-only", "original")
FAULTS = ("off-by-one",)
RUN1 = {"report": "experiments/results/evermembench_control_run1_superseded/evermembench_control.json",
        "rule": "original", "eligible": 2212, "all_required_hits": 117,
        "all_required_at_10": 117 / 2212, "unplanted_token_hits": 0, "passed": False}
Coordinate = tuple[str, str, int]


@dataclass
class Probe:
    query_id: str
    question: str
    token: str
    expected: list[frozenset[Coordinate]]
    planted: set[Coordinate]


def prepare_control(days: list, questions: list, fault: str | None = None) -> tuple[dict, list[Probe]]:
    """Select witnesses in the original message arrays, independently of the loader."""
    if fault is not None and fault not in FAULTS:
        raise ValueError(f"unknown fault: {fault}")
    suite = topic_memories(days, questions)
    source = {}
    for day in days:
        for group, messages in day["dialogues"].items():
            source[day["date"], group] = messages or []
            for msg in messages or []:
                if PREFIX in msg["dialogue"].lower():
                    raise ValueError("control token prefix already occurs in a source message")
                number = msg["message_index"]
                key = f"{day['date']}|{group}|{number}"
                row = suite["memories"][key]
                if (row["date"], row["channel"], row["message_index"], row["speaker"],
                    row["time"], row["content"]) != (
                    day["date"], group, number, msg["speaker"], msg["time"], msg["dialogue"]
                ):
                    raise ValueError(f"converted source message differs at {key}")

    probes = []
    for ordinal, q in enumerate(questions):
        if PREFIX in q["Q"].lower():
            raise ValueError("control token prefix already occurs in a source question")
        token = f"{PREFIX}{q['topic_id']}x{ordinal}"
        eligible = len(q["R"]) <= DEPTH
        groups, planted = [], set()
        for ref in q["R"]:
            day, group = ref["date"], ref["group"]
            # Test the indices on actual messages against the released intervals.
            # The converter instead expands each interval into lookup keys.
            intervals = [tuple(map(int, part.split("-")))
                         for part in str(ref["message_index"]).split(",")]
            matches = [msg for msg in source[day, group]
                       if any(bounds[0] <= msg["message_index"] <= bounds[-1]
                              for bounds in intervals)]
            if not matches:
                raise ValueError(f"{q['id']}: reference has no support in the source dialogues")
            groups.append(frozenset((day, group, msg["message_index"]) for msg in matches))
            if eligible:
                number = max(msg["message_index"] for msg in matches)
                if fault == "off-by-one":
                    number += 1
                    if not any(msg["message_index"] == number for msg in source[day, group]):
                        continue
                planted.add((day, group, number))
        probes.append(Probe(q["id"], q["Q"], token, groups, planted))
    return suite, probes


@contextmanager
def planted_fixture(store, witnesses, token):
    """Temporarily edit only witness text in this private, in-memory experiment."""
    update = "UPDATE memories SET content = ? WHERE id = ?"
    with store._transaction() as connection:
        connection.executemany(update, [(text + " " + token, mid) for mid, text in witnesses])
    try:
        yield
    finally:
        with store._transaction() as connection:
            connection.executemany(update, [(text, mid) for mid, text in witnesses])


def score_control(suite: dict, probes: list[Probe], rule: str = "token-only") -> dict:
    if rule not in RULES:
        raise ValueError(f"unknown rule: {rule}")
    coordinates = {key: (row["date"], row["channel"], row["message_index"])
                   for key, row in suite["memories"].items()}
    queries = {q["id"]: q for q in suite["queries"]}
    if set(queries) != {p.query_id for p in probes} or len(queries) != len(probes):
        raise ValueError("converted question IDs do not match the source")
    eligible = passed = cross_group = 0
    diagnostic = None
    failures = []
    with MemoryStore(":memory:") as store:
        originals = {}
        for key, row in suite["memories"].items():
            mem = store.add_memory(row["content"], row["kind"], source=key,
                                   channel=row["channel"], speaker=row["speaker"])
            originals[coordinates[key]] = mem.id, row["content"]
        for probe in probes:
            query = queries[probe.query_id]
            converted = [frozenset(coordinates[key] for key in keys)
                         for keys in query["required_groups"]]
            if converted != probe.expected:
                raise ValueError(f"{probe.query_id}: converted groups differ from source intervals")
            if len(converted) > DEPTH:
                continue
            if query["query"] != probe.question:
                raise ValueError(f"{probe.query_id}: original question did not round-trip")
            eligible += 1
            cross_group += "cross_group" in query["tags"]
            witnesses = [originals[coord] for coord in probe.planted]
            text = probe.token if rule == "token-only" else query["query"] + " " + probe.token
            with planted_fixture(store, witnesses, probe.token):
                hits = store.search(text, limit=DEPTH, record_access=False)
                retrieved = {coordinates[hit.memory.source] for hit in hits}
                if all(retrieved.intersection(group) for group in probe.expected):
                    passed += 1
                else:
                    failures.append(probe.query_id)
                    if diagnostic is None:
                        only = store.search(probe.token, limit=DEPTH, record_access=False)
                        token_hits = {coordinates[hit.memory.source] for hit in only}
                        diagnostic = {"question_id": probe.query_id,
                                      "exact_planted_set": token_hits == probe.planted,
                                      "all_required": all(token_hits.intersection(group)
                                                          for group in probe.expected)}
        absent_hits = len(store.search(PREFIX + "absent", limit=DEPTH, record_access=False))
    return {
        "topic": suite["id"], "messages": len(coordinates), "links": len(suite["links"]),
        "questions": len(probes), "eligible": eligible, "eligible_cross_group": cross_group,
        "over_ten_entries": len(probes) - eligible,
        "resolved_message_references": sum(len(group) for p in probes for group in p.expected),
        "all_required_hits": passed, "all_required_at_10": passed / eligible if eligible else None,
        "unplanted_token_hits": absent_hits, "failed_questions": len(failures),
        "first_failed_ids": failures[:5], "token_only_first_failure": diagnostic,
    }


def run_topic(args: tuple[Path, str, str, str | None]) -> dict:
    root, topic, rule, fault = args
    suite, probes = prepare_control(*read_topic_files(root, topic), fault=fault)
    if suite["id"] != topic:
        raise ValueError(f"expected topic {topic}, found {suite['id']}")
    result = score_control(suite, probes, rule)
    print(f"Topic {topic}: {result['all_required_hits']}/{result['eligible']}", file=sys.stderr,
          flush=True)
    return result


def render(report: dict) -> str:
    totals = report["totals"]
    lines = [
        "# EverMemBench loader control",
        "",
        "{}: rule `{}`{}; lexical all-required@10 {} of {} eligible questions ({:.3f}); "
        "unplanted token hits {}.".format(
            "**Fault detected**" if report["fault"] and not report["passed"]
            else "**Fault NOT detected**" if report["fault"]
            else "**Passed**" if report["passed"] else "**Failed**",
            report["rule"], "; injected fault `{}`".format(report["fault"]) if report["fault"] else "",
            totals["all_required_hits"], totals["eligible"], totals["all_required_at_10"],
            totals["unplanted_token_hits"]),
        "",
        "Criterion: {}".format(report["criterion"]),
        "",
        "Run 1 (rule `original`, superseded): {} of {} ({:.3f}), failed; see `{}`. The rule was "
        "changed on 2026-11-26 before this run; the docstring of "
        "`experiments/evermembench_control.py` records the deviation.".format(
            RUN1["all_required_hits"], RUN1["eligible"], RUN1["all_required_at_10"], RUN1["report"]),
        "",
        "| Topic | Messages | Questions | Eligible | Over ten entries | All required | Failed | "
        "Unplanted hits |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in report["topics"]:
        lines.append("| {topic} | {messages:,} | {questions:,} | {eligible:,} | {over_ten_entries:,} | "
                     "{all_required_hits:,} | {failed_questions:,} | {unplanted_token_hits} |"
                     .format(**row))
    lines += [
        "",
        "Dataset {} at revision `{}`; inputs and code pinned by SHA-256 in the JSON report. "
        "Python {}.".format(report["dataset"], report["revision"], report["python"]),
        "",
    ]
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data", type=Path, required=True,
                        help="local dataset root containing 01/ through 05/")
    parser.add_argument("--output", type=Path,
                        help="JSON report path; a Markdown report is written beside it")
    parser.add_argument("--workers", type=int, choices=range(1, 6), default=1,
                        help="independent topic processes")
    parser.add_argument("--rule", choices=RULES, default="token-only")
    parser.add_argument("--fault", choices=FAULTS)
    parser.add_argument("--topic", action="append", choices=sorted(FILE_HASHES),
                        help="run only these topics (repeatable; default all five)")
    args = parser.parse_args(argv)
    source_files = ("src/dynmemory/store.py", "src/dynmemory/evermembench.py",
                    "experiments/evermembench_control.py")
    hashes = {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in source_files}
    topics = args.topic or list(FILE_HASHES)
    jobs = [(args.data, topic, args.rule, args.fault) for topic in topics]
    if args.workers == 1:
        rows = list(map(run_topic, jobs))
    else:
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            rows = list(pool.map(run_topic, jobs))
    for path, digest in hashes.items():
        if digest != hashlib.sha256((ROOT / path).read_bytes()).hexdigest():
            raise RuntimeError(f"source file changed during run: {path}")
    fields = ("messages", "links", "questions", "eligible", "eligible_cross_group",
              "over_ten_entries", "resolved_message_references", "all_required_hits",
              "failed_questions", "unplanted_token_hits")
    totals = {key: sum(row[key] for row in rows) for key in fields}
    totals["all_required_at_10"] = totals["all_required_hits"] / totals["eligible"]
    passed = totals["all_required_at_10"] == 1.0 and totals["unplanted_token_hits"] == 0
    inputs = {f"{topic}/{name}": digest for topic, pair in FILE_HASHES.items()
              for name, digest in zip(("dialogue.json", f"qa_{topic}.json"), pair)}
    if args.rule == "token-only":
        criterion = ("For every question with at most ten R entries, the token-only query's "
                     "lexical top 10 covers every R entry; an unplanted token returns zero results.")
        control = ("Append one unique token to one raw message per reference entry and query the "
                   "token alone. Reset those messages before the next question. Full topic store, "
                   "no graph links or embedder.")
    else:
        criterion = "All eligible questions hit every R entry in lexical top 10."
        control = ("Append one unique token to the original question and one raw message per "
                   "reference entry. Reset those messages before the next question. Full topic "
                   "store, no graph links or embedder. A token-only query diagnoses the first "
                   "failure per topic. An unplanted token must return zero results.")
    report = {
        "dataset": DATASET, "revision": REVISION, "input_sha256": inputs,
        "code_sha256": hashes, "python": platform.python_version(),
        "rule": args.rule, "fault": args.fault, "topics_run": topics,
        "criterion": criterion, "control": control,
        "deviation": {"date": "2026-11-26", "from": "original", "to": "token-only",
                      "reason": "BM25 cannot rank one rare appended token above messages matching "
                                "several question words; long planted messages are penalised.",
                      "run1": RUN1},
        "passed": passed, "totals": totals, "topics": rows,
    }
    if args.fault:
        report["fault_detected"] = not passed
    data = json.dumps(report, indent=2) + "\n"
    if args.output:
        args.output.write_text(data, encoding="utf-8")
        args.output.with_suffix(".md").write_text(render(report), encoding="utf-8")
    else:
        print(data, end="")
    if args.fault:
        return 0 if not passed else 1
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
