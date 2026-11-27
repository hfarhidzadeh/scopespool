"""Audience noninterference on EverMemBench: does a search leak evidence from groups the asker cannot see?

Pre-registered 2026-11-26, before any recorded run. Smoke runs do not write into
``experiments/results/``.

Question. EverMemBench-Dynamic (pinned revision, five projects) has several chat
groups per project and named speakers, and 791 of its 2,400 questions cite
evidence from more than one group. Treating each group as a channel, can a
search for one member return, rank by, or be influenced by messages from a group
that member is not in?

Data and staging. Each project is loaded with ``dynmemory.evermembench`` (input
bytes checked against SHA-256). Every message becomes one episode memory in the
channel of its group, written as its speaker through ``for_writer``. Membership
is inferred: a speaker belongs to every group of the project in which they
posted at least once. Consecutive messages of one day and group are linked
``related_to``, as the loader provides. Lexical search only, limit 10, no
access recorded. Each message gets a fixed creation time from its position in
the project, so equal scores break the same way in every store.

Questions and askers. Only cross-group questions are used. For each, the asker
is a speaker who belongs to at least one but not all of the cited groups,
chosen with ``random.Random("<seed>-<question id>")`` from the sorted
candidates (seed 0). The asker is staged: the dataset names no asker.
Questions with no such speaker are skipped and counted.

Worlds, per question.
- FULL: the whole project store, searched with ``viewers=[asker]``.
- VISIBLE: a store holding only the messages and links of the asker's groups,
  searched with ``viewers=[asker]``.
- POWER: the FULL store searched by a synthetic member who belongs to every
  group, standing for the asker made a member of every group.

Rules, fixed before running.
  1. Determinism (negative control): project 01 is processed twice from
     scratch (asker choice, stores, rankings) for its first 50 cross-group
     questions, or all of them in a smoke run's subset; both passes are equal.
  2. Power (positive control): POWER's top 10 holds at least one cited message
     from a group the asker cannot see in at least 25% of questions. Below
     that, hidden evidence rarely ranks at all and rules 3 and 4 would hold
     vacuously. 25% of 791 still gives about 200 questions able to show a leak.
  3. Noninterference: for every question, FULL and VISIBLE return the same
     message keys in the same order, with scores equal within 1e-9.
  4. No hidden message: no message from a group the asker is not in appears in
     FULL's top 10, for any question.
Verdict: "inconclusive (control <n> failed)" if rule 1 or 2 fails; otherwise
"no leak across groups" if rules 3 and 4 hold for every question, else
"leak (rules <list> failed, first failing question <id>)".

Reported, not part of the verdict: all-required@10 over the cited groups the
asker can see (FULL's top 10 has a message from each such group); askers per
project; skipped questions.

Validation, fixed before running: ``--fault leak`` makes FULL search without
viewers. Rules 3 and 4 must then each fail in at least 25% of questions, or
this experiment cannot detect the leak it is for.

Limits. The asker is staged; membership is inferred from who posted, so members
who never posted are missing; membership is not dated, so a member reads the
whole history of a group; there is no roster; group names such as "Group 3"
only mean something within one project; lexical search only.

N-gram variant, added 2026-11-27 before any n-gram run on real data.
``--embedder ngram`` runs the same workload (same projects, questions, askers,
seed, stores, links, creation times, limit 10, no access recorded) with every
store built with ``dynmemory.NGramHashEmbedder()`` at its defaults (character
3-grams hashed into 512 dimensions, ``min_similarity`` 0.25). Each message is
embedded when written. Search is then hybrid: the lexical ranking and the
cosine ranking are fused by reciprocal rank fusion, the fused scores are
divided by the top one, and results are expanded by one link hop. Without the
option nothing changes: lexical search, no embedder constructed.
Rules for the variant: the same four rules, verdict and fault criterion as
above, with the same 1e-9 score tolerance. No rule needs to differ. With
``viewers``, the store drops hidden memories before ranking on both paths; a
cosine similarity depends only on the query vector and that memory's own
stored vector (float32, made from the same text in FULL and VISIBLE); and the
fusion ranks, the division by the top score and the link hop are all computed
over the visible memories. FULL and VISIBLE should therefore produce identical
numbers in the same order, so any score difference above rounding means that
hidden memories moved a visible score, which is the leak rule 3 is for; a
wider tolerance would hide exactly that. Rule 2 (power) is re-measured with
hybrid search and keeps its 25% threshold; if hybrid POWER falls below it, the
variant is inconclusive, not passed. Reports record the embedder. Limit of the
variant: the n-gram embedder is a spelling baseline, not a semantic model, so
this tests the vector path's isolation, not a semantic embedder's.

Run from the repository root, with the pinned dataset checkout:

    python3 -I experiments/evermembench_audience.py --data /path/to/EverMemBench-Dynamic
    python3 -I experiments/evermembench_audience.py --data /path/to/EverMemBench-Dynamic \\
        --fault leak --output experiments/results/evermembench_audience_fault
    python3 -I experiments/evermembench_audience.py --data /path/to/EverMemBench-Dynamic \\
        --smoke --output /tmp/evermembench_audience_smoke
    python3 -I experiments/evermembench_audience.py --data /path/to/EverMemBench-Dynamic \\
        --embedder ngram --output /tmp/evermembench_audience_ngram
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from dynmemory import MemoryStore  # noqa: E402
from dynmemory import evermembench  # noqa: E402

TOPICS = ("01", "02", "03", "04", "05")
LIMIT = 10
SEED = 0
TOLERANCE = 1e-9
POWER_SHARE = 0.25
FAULT_SHARE = 0.25
DETERMINISM_QUESTIONS = 50
SMOKE_TOPIC, SMOKE_QUESTIONS = "01", 40
POWER_VIEWER = "__every_group__"
CLOCK_BASE = datetime(2020, 1, 1, tzinfo=timezone.utc)
CHECKS = ("determinism", "power", "noninterference", "no_hidden")
RESULTS = ROOT / "experiments" / "results"
EMBEDDERS = {
    "ngram": "NGramHashEmbedder, character 3-grams, 512 dimensions, min_similarity 0.25",
}
SOURCES = {
    "script": Path(__file__).resolve(),
    "store": ROOT / "src" / "dynmemory" / "store.py",
    "loader": ROOT / "src" / "dynmemory" / "evermembench.py",
}


def channel_of(key: str) -> str:
    return key.split("|")[1]


def memberships(suite: dict) -> dict:
    groups = {}
    for memory in suite["memories"].values():
        groups.setdefault(memory["speaker"], set()).add(memory["channel"])
    return groups


def choose_asker(query: dict, members: dict, seed: int):
    cited = {channel_of(group[0]) for group in query["required_groups"]}
    candidates = sorted(
        speaker for speaker, groups in members.items()
        if groups & cited and not cited <= groups
    )
    if not candidates:
        return None
    return random.Random("{}-{}".format(seed, query["id"])).choice(candidates)


def make_embedder(name):
    """None (lexical search) or a fresh embedder for this name."""
    if name is None:
        return None
    if name != "ngram":
        raise ValueError("unknown embedder: {}".format(name))
    from dynmemory import NGramHashEmbedder  # the same package as MemoryStore
    return NGramHashEmbedder()


def build_store(suite: dict, channels=None, power_viewer: bool = False, embedder=None):
    """A store of the suite's messages in ``channels`` (all if None), written as their speakers."""
    keys = list(suite["memories"])
    ordinal = {key: number for number, key in enumerate(keys, start=1)}
    included = [key for key in keys
                if channels is None or suite["memories"][key]["channel"] in channels]
    store = MemoryStore(":memory:", embedder=make_embedder(embedder))
    store._now = lambda: CLOCK_BASE.isoformat(timespec="microseconds")
    members = sorted({(suite["memories"][key]["channel"], suite["memories"][key]["speaker"])
                      for key in included})
    for channel, speaker in members:
        store.join_channel(channel, speaker)
    if power_viewer:
        for channel in sorted({channel for channel, _ in members}):
            store.join_channel(channel, POWER_VIEWER)
    id_to_key, key_to_id = {}, {}
    for key in included:
        memory = suite["memories"][key]
        stamp = (CLOCK_BASE + timedelta(microseconds=ordinal[key])).isoformat(
            timespec="microseconds")
        store._now = lambda stamp=stamp: stamp
        written = store.for_writer(memory["speaker"]).add_memory(
            memory["content"], "episode", channel=memory["channel"])
        id_to_key[written.id], key_to_id[key] = key, written.id
    for link in suite["links"]:
        if link["source"] in key_to_id and link["target"] in key_to_id:
            store.relate(key_to_id[link["source"]], key_to_id[link["target"]], link["relation"])
    del store._now
    return store, id_to_key


def ranked(store, id_to_key, query: str, viewers):
    if viewers is None:
        results = store.search(query, limit=LIMIT, record_access=False)
    else:
        results = store.search(query, limit=LIMIT, viewers=viewers)
    return [id_to_key[result.memory.id] for result in results], [result.score for result in results]


def same_ranking(left_keys, left_scores, right_keys, right_scores) -> bool:
    return left_keys == right_keys and all(
        abs(a - b) <= TOLERANCE for a, b in zip(left_scores, right_scores))


def run_suite(suite: dict, *, seed: int = SEED, fault=None, limit=None, embedder=None) -> dict:
    members = memberships(suite)
    queries = [query for query in suite["queries"] if "cross_group" in query.get("tags", ())]
    if limit is not None:
        queries = queries[:limit]
    full, full_ids = build_store(suite, power_viewer=True, embedder=embedder)
    visible_stores, rows, skipped = {}, [], []
    try:
        for query in queries:
            asker = choose_asker(query, members, seed)
            if asker is None:
                skipped.append(query["id"])
                continue
            groups = frozenset(members[asker])
            if groups not in visible_stores:
                visible_stores[groups] = build_store(suite, channels=groups, embedder=embedder)
            visible, visible_ids = visible_stores[groups]
            full_keys, full_scores = ranked(
                full, full_ids, query["query"], None if fault == "leak" else [asker])
            visible_keys, visible_scores = ranked(visible, visible_ids, query["query"], [asker])
            power_keys, _ = ranked(full, full_ids, query["query"], [POWER_VIEWER])
            hidden_groups = [set(group) for group in query["required_groups"]
                             if channel_of(group[0]) not in groups]
            seen_groups = [set(group) for group in query["required_groups"]
                           if channel_of(group[0]) in groups]
            top = set(full_keys)
            rows.append({
                "id": query["id"], "asker": asker, "asker_groups": sorted(groups),
                "full": full_keys, "visible": visible_keys,
                "noninterference": same_ranking(full_keys, full_scores,
                                                visible_keys, visible_scores),
                "no_hidden": all(channel_of(key) in groups for key in full_keys),
                "power": any(set(power_keys) & group for group in hidden_groups),
                "all_required_visible": all(top & group for group in seen_groups),
            })
    finally:
        full.close()
        for store, _ in visible_stores.values():
            store.close()
    return {"topic": suite["id"], "rows": rows, "skipped": skipped,
            "askers": len({row["asker"] for row in rows})}


def summarise(topics: list, determinism: bool) -> dict:
    rows = [row for topic in topics for row in topic["rows"]]
    total = len(rows)

    def failing(name):
        return [row["id"] for row in rows if not row[name]]

    return {
        "questions": total,
        "skipped": sum(len(topic["skipped"]) for topic in topics),
        "determinism": determinism,
        "power_held": sum(row["power"] for row in rows),
        "noninterference_failed": failing("noninterference"),
        "no_hidden_failed": failing("no_hidden"),
        "all_required_visible": (sum(row["all_required_visible"] for row in rows) / total
                                 if total else None),
        "per_topic": {topic["topic"]: {"questions": len(topic["rows"]),
                                       "skipped": len(topic["skipped"]),
                                       "askers": topic["askers"]} for topic in topics},
    }


def decide(summary: dict) -> dict:
    total = summary["questions"]
    holds = {
        1: summary["determinism"],
        2: total > 0 and summary["power_held"] >= POWER_SHARE * total,
        3: not summary["noninterference_failed"],
        4: not summary["no_hidden_failed"],
    }
    failed_controls = [n for n in (1, 2) if not holds[n]]
    if failed_controls:
        verdict = "inconclusive (control {} failed)".format(", ".join(map(str, failed_controls)))
    elif holds[3] and holds[4]:
        verdict = "no leak across groups"
    else:
        first = (summary["noninterference_failed"] + summary["no_hidden_failed"])[0]
        verdict = "leak (rules {} failed, first failing question {})".format(
            ", ".join(str(n) for n in (3, 4) if not holds[n]), first)
    decision = {"rule_{}_{}".format(n, name): holds[n] for n, name in enumerate(CHECKS, start=1)}
    decision["verdict"] = verdict
    return decision


def validate_fault(summary: dict) -> dict:
    total = summary["questions"]
    rule3 = len(summary["noninterference_failed"])
    rule4 = len(summary["no_hidden_failed"])
    return {"rule_3_failed": rule3, "rule_4_failed": rule4, "questions": total,
            "detected": total > 0 and rule3 >= FAULT_SHARE * total
            and rule4 >= FAULT_SHARE * total}


def check_determinism(suite: dict, limit, fault, embedder=None) -> bool:
    count = DETERMINISM_QUESTIONS if limit is None else min(limit, DETERMINISM_QUESTIONS)
    first = run_suite(suite, fault=fault, limit=count, embedder=embedder)
    second = run_suite(suite, fault=fault, limit=count, embedder=embedder)
    return first == second


def _share(count, total) -> str:
    return "{} of {} ({:.1f}%)".format(count, total, 100.0 * count / total) if total else "-"


def search_mode(report: dict) -> str:
    name = report.get("embedder")
    if name is None:
        return "lexical search"
    return "hybrid search (lexical + {} `{}`)".format(EMBEDDERS[name], report["embedder_model"])


def render(report: dict) -> str:
    summary, decision = report["summary"], report["decision"]
    total = summary["questions"]
    lines = [
        "# EverMemBench audience noninterference",
        "",
        "{}Projects {}; {} cross-group questions ({} skipped, no eligible asker); seed {}; "
        "{}, limit 10{}.".format(
            "SMOKE RUN, not a recorded result. " if report["smoke"] else "",
            ", ".join(report["topics"]), total, summary["skipped"], report["seed"],
            search_mode(report),
            "; injected fault: {}".format(report["fault"]) if report["fault"] else ""),
        "See the docstring of `experiments/evermembench_audience.py` for the design and rules.",
        "",
        "Verdict: **{}**".format(decision["verdict"]),
        "",
        "| Rule | Check | Held | Needed |",
        "| --- | --- | --- | --- |",
        "| 1 | Determinism (project 01 processed twice) | {} | equal |".format(
            "yes" if summary["determinism"] else "no"),
        "| 2 | Power: POWER ranks hidden cited evidence in its top 10 | {} | at least 25% |".format(
            _share(summary["power_held"], total)),
        "| 3 | Noninterference: FULL equals VISIBLE | {} | every question |".format(
            _share(total - len(summary["noninterference_failed"]), total)),
        "| 4 | No hidden-group message in FULL's top 10 | {} | every question |".format(
            _share(total - len(summary["no_hidden_failed"]), total)),
        "",
        "All-required@10 over the cited groups the asker can see: {}.".format(
            "-" if summary["all_required_visible"] is None
            else "{:.3f}".format(summary["all_required_visible"])),
        "",
        "| Project | Questions | Skipped | Distinct askers |",
        "| --- | ---: | ---: | ---: |",
    ]
    for topic, item in summary["per_topic"].items():
        lines.append("| {} | {} | {} | {} |".format(
            topic, item["questions"], item["skipped"], item["askers"]))
    if report.get("validation"):
        check = report["validation"]
        lines += ["", "Fault validation: rule 3 failed in {}, rule 4 in {}; needed at least "
                  "25% each: {}.".format(
                      _share(check["rule_3_failed"], check["questions"]),
                      _share(check["rule_4_failed"], check["questions"]),
                      "detected" if check["detected"] else "NOT detected")]
    lines += [
        "",
        "Limits: the asker is staged, membership is inferred from who posted and is not "
        "dated, there is no roster, and group names only mean something within a project.",
        "",
        "Python {}; sources: {}.".format(report["python"], ", ".join(
            "{} `{}`".format(name, digest[:12]) for name, digest in report["source_sha256"].items())),
        "",
    ]
    return "\n".join(lines)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main(argv=None, loader=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data", type=Path)
    parser.add_argument("--topic", action="append", choices=TOPICS)
    parser.add_argument("--smoke", action="store_true",
                        help="project 01, first 40 cross-group questions; never writes results/")
    parser.add_argument("--fault", choices=["leak"])
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--embedder", choices=sorted(EMBEDDERS),
                        help="hybrid search with this embedder (default: lexical search only)")
    parser.add_argument("--output", type=Path, default=RESULTS / "evermembench_audience")
    arguments = parser.parse_args(argv)
    output = arguments.output.resolve()
    if arguments.smoke and (output == RESULTS.resolve() or RESULTS.resolve() in output.parents):
        parser.error("a smoke run cannot write into experiments/results/")
    if loader is None:
        if arguments.data is None:
            parser.error("--data is required")
        loader = lambda topic: evermembench.load_topic(arguments.data, topic)  # noqa: E731
    topics = [SMOKE_TOPIC] if arguments.smoke else (arguments.topic or list(TOPICS))
    limit = SMOKE_QUESTIONS if arguments.smoke else None
    hashes = {name: sha256(path) for name, path in SOURCES.items()}
    suites = {topic: loader(topic) for topic in topics}
    results = [run_suite(suites[topic], seed=arguments.seed, fault=arguments.fault, limit=limit,
                         embedder=arguments.embedder)
               for topic in topics]
    determinism = check_determinism(suites[topics[0]], limit, arguments.fault, arguments.embedder)
    if {name: sha256(path) for name, path in SOURCES.items()} != hashes:
        raise RuntimeError("a source file changed during the run")
    summary = summarise(results, determinism)
    report = {
        "topics": topics, "seed": arguments.seed, "fault": arguments.fault,
        "smoke": arguments.smoke, "embedder": arguments.embedder,
        "embedder_model": (make_embedder(arguments.embedder).name
                           if arguments.embedder else None),
        "summary": summary, "decision": decide(summary),
        "dataset_revision": evermembench.REVISION, "python": platform.python_version(),
        "source_sha256": hashes,
        "questions": [{key: row[key] for key in ("id", "asker", "asker_groups", "noninterference",
                                                 "no_hidden", "power", "all_required_visible")}
                      for topic in results for row in topic["rows"]],
    }
    if arguments.fault:
        report["validation"] = validate_fault(summary)
    text = render(report)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.with_suffix(".json").write_text(json.dumps(report, indent=2) + "\n")
    output.with_suffix(".md").write_text(text)
    print(text)
    if arguments.fault:
        return 0 if report["validation"]["detected"] else 1
    return 0 if report["decision"]["verdict"] == "no leak across groups" else 1


if __name__ == "__main__":
    sys.exit(main())
