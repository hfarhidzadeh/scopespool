"""Verify the SocialMemBench loader's evidence keys on the pinned release.

Rule, fixed 2026-11-27 before this control ran on the real data.

Achievability was measured first, independently of this loader: pyarrow 17
read the pinned release (all 1,031 questions, 1,979 evidence anchors; the full
check took seconds, so no sample was drawn). Every anchor's ``turn_id``
resolved to a turn of the question's network, and every ``message_excerpt``
was an exact substring of that turn's message (1,979 of 1,979, no
normalisation). Three anchors disagree with their turn on a stated field and
are listed in ``KNOWN_DISAGREEMENTS``: two name a different speaker and one a
different session. The rule is therefore set at 1.0, with only those three
excluded, and only from the attribution check:

A. Evidence resolution. For every anchor of every question: (1) the loader's
   evidence key equals the raw ``turn_id`` (parsed here from the raw JSON, not
   by the loader); (2) the key names a loaded turn whose text contains the raw
   excerpt verbatim; (3) the anchor's ``speaker_display_name`` and
   ``session_index`` equal the loaded turn's, except the three known anchors.
   Each count must be 1,979 of 1,979 (attribution: 1,976 of 1,976 checked).
B. Canary. For each question, an independent reader finds each anchored turn
   by its ``turn_id`` in the raw conversation rows and appends one unique token
   to it in a full-network in-memory store (no links, no embedder). The rows
   are restored before the next question. The token-only lexical search (limit
   ten, or the number of evidence turns if larger) must return exactly the
   loader's evidence keys for that question: no more, no fewer. An unplanted
   token must return zero results in every network.

The control passes only if A and B both hold for every question.

Faults, fixed 2026-11-27 before the real-data run. Each fault rewrites the
loader's output to simulate a bug, so the rule must fail:
``off-by-one`` maps every evidence key to the next turn of its session (a
0-/1-based mix-up; at the end of a session the key resolves to nothing).
``turn-suffix`` resolves each ``turn_id`` by parsing ``_sNN_tNNN`` as a
session index and a zero-based message index. That shortcut agrees with the
data for most turns, but the suffix and ``message_index`` disagree for 1,319
turns (offset 0 for 1,315, offset -2 for 4), so it should fail on a minority
of anchors.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import re
import sys
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from dynmemory.socialmembench import DATASET, FILE_HASHES, LICENSE, REVISION, build_networks, read_release
from dynmemory.store import MemoryStore

DEPTH = 10
PREFIX = "scopespoolsocialcanary"
FAULTS = ("off-by-one", "turn-suffix")
# (network_id, qa_id, turn_id): what the anchor states vs what the turn holds.
KNOWN_DISAGREEMENTS = {
    ("grp_d3e4f5a6", "Q8_8a371f10", "grp_d3e4f5a6_s02_t009"): "anchor speaker Quinn, turn speaker Pat",
    ("grp_d3e4f5a6", "Q8_0e6c7026", "grp_d3e4f5a6_s10_t023"): "anchor speaker Nico, turn speaker Pat",
    ("grp_e3f4a5b6", "Q8_5fd3bd95", "grp_e3f4a5b6_s04_t003"): "anchor session 1, turn in session 4",
}
SUFFIX = re.compile(r"_s(\d+)_t(\d+)")


@dataclass
class Probe:
    network: str
    query_id: str
    token: str
    anchors: list  # raw (turn_id, excerpt, speaker, session_index) per anchor
    witnesses: list  # raw (session_id, message_index) of each distinct anchored turn


def apply_fault(suite: dict, fault: str) -> None:
    """Rewrite the loader's evidence keys in place to simulate a turn-mapping bug."""
    memories = suite["memories"]
    by_coordinate = {(m["session_index"], m["message_index"]): key for key, m in memories.items()}
    if fault == "off-by-one":
        def remap(key):
            m = memories[key]
            return by_coordinate.get((m["session_index"], m["message_index"] + 1))
    elif fault == "turn-suffix":
        def remap(key):
            match = SUFFIX.search(key)
            return by_coordinate.get((int(match[1]), int(match[2]) + 1)) if match else None
    else:
        raise ValueError(f"unknown fault: {fault}")
    for query in suite["queries"]:
        for entry in query["evidence"]:
            entry["key"] = remap(entry["key"])
        keys = list(dict.fromkeys(entry["key"] for entry in query["evidence"]))
        query["relevant"] = keys
        query["required_groups"] = [[key] for key in keys]


def prepare_control(conversations: list, qa: list, fault: str | None = None) -> tuple[list, list]:
    """Convert with the loader, and build probes from the raw rows independently of it."""
    if fault is not None and fault not in FAULTS:
        raise ValueError(f"unknown fault: {fault}")
    suites = build_networks(conversations, qa)
    if fault:
        for suite in suites:
            apply_fault(suite, fault)
    raw = {}
    for row in conversations:
        if PREFIX in row["message"].lower():
            raise ValueError("control token prefix already occurs in a source message")
        raw[row["turn_id"]] = row
    probes = []
    for ordinal, item in enumerate(qa):
        if PREFIX in item["question"].lower():
            raise ValueError("control token prefix already occurs in a source question")
        anchors = [(a["turn_id"], a["message_excerpt"], a.get("speaker_display_name"),
                    a.get("session_index")) for a in json.loads(item["evidence_anchors_json"])]
        witnesses = []
        for turn_id in dict.fromkeys(a[0] for a in anchors):
            row = raw.get(turn_id)
            if row is None or row["network_id"] != item["network_id"]:
                raise ValueError(f"{item['qa_id']}: raw turn {turn_id!r} is not in its network")
            witnesses.append((row["session_id"], row["message_index"]))
        probes.append(Probe(item["network_id"], item["qa_id"], f"{PREFIX}q{ordinal}", anchors, witnesses))
    return suites, probes


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


def score_network(suite: dict, probes: list) -> dict:
    memories = suite["memories"]
    queries = {q["id"]: q for q in suite["queries"]}
    if sorted(queries) != sorted(p.query_id for p in probes):
        raise ValueError(f"{suite['id']}: converted question IDs do not match the source")
    counts = dict(anchors=0, key_roundtrip=0, excerpt_verbatim=0, attribution_checked=0,
                  attribution_agree=0, canary_passed=0)
    attribution_failures, known_seen, failed = [], [], []
    with MemoryStore(":memory:") as store:
        rows = {}
        for key, m in memories.items():
            mem = store.add_memory(m["content"], m["kind"], source=key, channel=m["channel"],
                                   speaker=m["speaker"])
            rows[m["session_id"], m["message_index"]] = (mem.id, m["content"])
        for probe in probes:
            query = queries[probe.query_id]
            if len(query["evidence"]) != len(probe.anchors):
                raise ValueError(f"{probe.query_id}: anchor count differs from the source")
            ok = True
            for entry, (turn_id, excerpt, speaker, session) in zip(query["evidence"], probe.anchors):
                counts["anchors"] += 1
                key = entry["key"]
                turn = memories.get(key)
                good = key == turn_id
                counts["key_roundtrip"] += good
                verbatim = turn is not None and excerpt in turn["content"]
                counts["excerpt_verbatim"] += verbatim
                ok &= good and verbatim
                ident = (suite["id"], probe.query_id, turn_id)
                agree = turn is not None and (speaker, session) == (turn["speaker"], turn["session_index"])
                if ident in KNOWN_DISAGREEMENTS:
                    known_seen.append({"network": ident[0], "qa_id": ident[1], "turn_id": ident[2],
                                       "agrees": agree})
                    continue
                counts["attribution_checked"] += 1
                counts["attribution_agree"] += agree
                if not agree:
                    ok = False
                    attribution_failures.append(list(ident))
            witnesses = [rows[coordinate] for coordinate in probe.witnesses]
            limit = max(DEPTH, len(query["relevant"]))
            with planted_fixture(store, witnesses, probe.token):
                hits = {hit.memory.source for hit in store.search(probe.token, limit=limit,
                                                                  record_access=False)}
            if hits == set(query["relevant"]):
                counts["canary_passed"] += 1
            else:
                ok = False
            if not ok:
                failed.append(probe.query_id)
        absent = len(store.search(PREFIX + "absent", limit=DEPTH, record_access=False))
    return {"network": suite["id"], "turns": len(memories), "sessions":
            len({m["session_id"] for m in memories.values()}), "questions": len(probes),
            **counts, "unplanted_token_hits": absent, "failed_questions": len(failed),
            "first_failed_ids": failed[:5], "attribution_failures": attribution_failures[:5],
            "known_disagreements_seen": known_seen}


def run_control(conversations: list, qa: list, fault: str | None = None) -> dict:
    suites, probes = prepare_control(conversations, qa, fault)
    grouped = {}
    for probe in probes:
        grouped.setdefault(probe.network, []).append(probe)
    rows = []
    for suite in suites:
        rows.append(score_network(suite, grouped.get(suite["id"], [])))
        print(f"{suite['id']}: canary {rows[-1]['canary_passed']}/{rows[-1]['questions']}",
              file=sys.stderr, flush=True)
    fields = ("turns", "sessions", "questions", "anchors", "key_roundtrip", "excerpt_verbatim",
              "attribution_checked", "attribution_agree", "canary_passed", "unplanted_token_hits",
              "failed_questions")
    totals = {key: sum(row[key] for row in rows) for key in fields}
    totals["networks"] = len(rows)
    known = [k for row in rows for k in row["known_disagreements_seen"]]
    passed = (totals["anchors"] > 0
              and totals["key_roundtrip"] == totals["excerpt_verbatim"] == totals["anchors"]
              and totals["attribution_agree"] == totals["attribution_checked"]
              and totals["canary_passed"] == totals["questions"]
              and totals["unplanted_token_hits"] == 0)
    return {"passed": passed, "totals": totals, "known_disagreements_seen": known, "networks": rows}


def _rate(n, d):
    return f"{n:,} of {d:,} ({n / d:.3f})" if d else "n/a"


def render(report: dict) -> str:
    t = report["totals"]
    verdict = ("**Fault detected**" if report["fault"] and not report["passed"]
               else "**Fault NOT detected**" if report["fault"]
               else "**Passed**" if report["passed"] else "**Failed**")
    lines = [
        "# SocialMemBench loader control", "",
        verdict + (f"; injected fault `{report['fault']}`" if report["fault"] else "") + ".", "",
        f"- Evidence keys equal the raw turn IDs: {_rate(t['key_roundtrip'], t['anchors'])} anchors",
        f"- Key names a turn containing the excerpt verbatim: {_rate(t['excerpt_verbatim'], t['anchors'])}",
        f"- Anchor speaker and session agree with the turn: {_rate(t['attribution_agree'], t['attribution_checked'])}"
        f" (three known disagreements excluded)",
        f"- Canary returns exactly the evidence turns: {_rate(t['canary_passed'], t['questions'])} questions",
        f"- Unplanted token hits: {t['unplanted_token_hits']}",
        f"- Questions failing any part: {t['failed_questions']:,}", "",
        f"Criterion: {report['criterion']}", "",
        "| Network | Turns | Questions | Anchors | Key = turn ID | Excerpt verbatim | Canary | Unplanted |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for r in report["networks"]:
        lines.append(f"| {r['network']} | {r['turns']} | {r['questions']} | {r['anchors']} | "
                     f"{r['key_roundtrip']} | {r['excerpt_verbatim']} | {r['canary_passed']} | "
                     f"{r['unplanted_token_hits']} |")
    lines += ["", f"Dataset {report['dataset']} ({report['license']}) at revision `{report['revision']}`; "
              f"input and code SHA-256 in the JSON report. Python {report['python']}.", ""]
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data", type=Path, required=True,
                        help="local directory holding conversations.parquet and qa.parquet")
    parser.add_argument("--output", type=Path,
                        help="JSON report path; a Markdown report is written beside it")
    parser.add_argument("--fault", choices=FAULTS)
    args = parser.parse_args(argv)
    source_files = ("src/dynmemory/store.py", "src/dynmemory/socialmembench.py",
                    "experiments/socialmembench_control.py")
    hashes = {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in source_files}
    tables = read_release(args.data)
    result = run_control(tables["conversations"], tables["qa"], args.fault)
    for path, digest in hashes.items():
        if digest != hashlib.sha256((ROOT / path).read_bytes()).hexdigest():
            raise RuntimeError(f"source file changed during run: {path}")
    report = {
        "dataset": DATASET, "license": LICENSE, "revision": REVISION,
        "input_sha256": {name: FILE_HASHES[name] for name in ("conversations.parquet", "qa.parquet")},
        "code_sha256": hashes, "python": platform.python_version(), "fault": args.fault,
        "rule_date": "2026-11-27",
        "criterion": ("Every anchor: loader key equals the raw turn_id and names a turn containing "
                      "the excerpt verbatim; speaker and session agree except the three known "
                      "anchors. Every question: the token-only lexical search returns exactly the "
                      "loader's evidence keys. An unplanted token returns zero results."),
        "known_disagreements": [{"network": n, "qa_id": q, "turn_id": t, "note": note}
                                for (n, q, t), note in KNOWN_DISAGREEMENTS.items()],
        **result,
    }
    if args.fault:
        report["fault_detected"] = not result["passed"]
    data = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.write_text(data, encoding="utf-8")
        args.output.with_suffix(".md").write_text(render(report), encoding="utf-8")
    else:
        print(data, end="")
    if args.fault:
        return 0 if not result["passed"] else 1
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
