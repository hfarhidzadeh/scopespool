"""EverMemBench retrieval: does hybrid ranking or session links find all cited evidence?

STATUS: DRAFT, 2026-11-26, for the researcher's approval. Nothing below has been
run on the full data. The script refuses to write a recorded report unless
``--approved`` is passed; ``--smoke`` runs a small subset and refuses to write
into ``experiments/results/``.

Data. EverMemBench-Dynamic, the five pinned topics, loaded by
``dynmemory.evermembench`` (keys ``date|group|message_index``; one required
group of alternative messages per R entry; links join consecutive messages of
one day and group). One store per topic holds every message of that topic.
Every question's original text is the query; answers are never used.

Configurations, each searching with limit 10 and no ``record_access``:
lexical; lexical with the session links; hybrid; hybrid with the session links.
Hybrid uses ``NGramHashEmbedder`` (``--hybrid minilm`` uses all-MiniLM-L6-v2 if
it is available offline; record which).

Measures per question: all-required@10 (every R group has a message in the top
10), group coverage@10 (share of R groups with a message in the top 10), and
first-hit reciprocal rank (first message of any group, depth 10).

Cohorts by the number of R groups: 1, 2-3, 4-10, and more than 10. Questions
with more than ten groups cannot reach all-required@10 in a top 10; they are
excluded from every all-required figure and reported by group coverage and
reciprocal rank only. Also reported: the question ID prefix (F_SH, F_MH, F_TP,
MA_P, MA_C, MA_U, P_Title, P_Style, P_Skill; the meaning is the benchmark's),
and single-group against cross-group evidence (the loader's tags).

Controls, all required before any reading:
  C0 canary: the loader control (``experiments/evermembench_control.py``, rule
     token-only) passes on the same questions and the same code, run here or
     accepted from ``--control-report`` only when its rule, topics, input
     hashes and code hashes match the current files.
  C1 oracle (positive): a ranking made of one message from each R group scores
     all-required@10 = 1.0 for every eligible question, through the same
     scoring function as the real runs.
  C2 shuffled assignment (negative): each topic's questions are searched in the
     next topic's store (01 in 02, ..., 05 in 01), lexical, no links. Over
     eligible questions all-required@10 must be at most 0.02 and group
     coverage@10 at most 0.10.

Readings, paired per eligible question over all five topics, each a mean
change with a 95% paired bootstrap interval (10,000 resamples) and a two-sided
sign-flip test (exact up to 16 non-zero changes, otherwise 100,000 flips),
as in ``experiments/longmemeval_v3.py``:
  A. hybrid minus lexical, links off, all-required@10.
  B. lexical with links minus lexical, all-required@10.
The two p-values are adjusted by Holm's method at a family level of 0.05.

Decision rule, fixed before running: "inconclusive (control <list> failed)" if
any of C0-C2 fails. Otherwise each reading is "helps" (adjusted p < 0.05 and
mean > 0), "hurts" (adjusted p < 0.05 and mean < 0) or "no clear effect".
Cohort, prefix and group-span tables, group coverage and reciprocal rank are
reported, with bootstrap intervals for A and B, and are not part of the
verdict.

Limits. Lexical and n-gram ranking only by default; the query is the full
question, which mixes cue words with filler; one store per topic means no
cross-topic distractors; message-level evidence is cited by the benchmark, not
by us.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import platform
import re
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from dynmemory import NGramHashEmbedder  # noqa: E402
from dynmemory.evaluation import CachedEmbedder, _build_store  # noqa: E402
from dynmemory.evermembench import DATASET, FILE_HASHES, REVISION, read_topic_files, topic_memories  # noqa: E402

DEPTH = 10
TOPICS = tuple(sorted(FILE_HASHES))
CONFIGS = (("lexical", False), ("lexical+links", True), ("hybrid", False), ("hybrid+links", True))
COHORTS = ("1", "2-3", "4-10", ">10")
SHUFFLE_ALL_REQUIRED = 0.02
SHUFFLE_COVERAGE = 0.10
FAMILY_ALPHA = 0.05
SMOKE_QUESTIONS = 40
DRAFT_DATE = "2026-11-26"
SOURCES = ("src/dynmemory/store.py", "src/dynmemory/evaluation.py", "src/dynmemory/evermembench.py",
           "experiments/evermembench_retrieval.py", "experiments/evermembench_control.py")


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


STATS = _load("ku_stats", ROOT / "experiments" / "longmemeval_knowledge_update.py")
CONTROL = _load("evermembench_control_for_retrieval", ROOT / "experiments" / "evermembench_control.py")


def cohort(groups: int) -> str:
    return "1" if groups == 1 else "2-3" if groups <= 3 else "4-10" if groups <= DEPTH else ">10"


def question_type(question_id: str) -> str:
    match = re.fullmatch(r"(.+)_Top\d+_\d+", question_id)
    return match.group(1) if match else "other"


def score(groups: list, relevant: list, retrieved: list) -> dict:
    """The one scoring function for real runs and controls."""
    top = retrieved[:DEPTH]
    hits = [any(key in top for key in group) for group in groups]
    wanted = set(relevant)
    return {
        "all_required": float(all(hits)) if len(groups) <= DEPTH else None,
        "group_coverage": sum(hits) / len(hits),
        "rr": next((1.0 / rank for rank, key in enumerate(top, start=1) if key in wanted), 0.0),
    }


def describe(suite: dict) -> list:
    return [{"topic": suite["id"], "id": query["id"], "groups": len(query["required_groups"]),
             "cohort": cohort(len(query["required_groups"])), "type": question_type(query["id"]),
             "span": "cross_group" if "cross_group" in query["tags"] else "single_group"}
            for query in suite["queries"]]


def oracle(suite: dict) -> list:
    return [score(q["required_groups"], q["relevant"], [group[0] for group in q["required_groups"]])
            for q in suite["queries"]]


def search_rows(suite: dict, queries: list, links: bool, embedder) -> list:
    """Search ``queries`` in ``suite``'s store; score against the queries' own groups."""
    with _build_store(suite, suite["links"] if links else [], embedder) as (store, ids):
        keys = {memory_id: key for key, memory_id in ids.items()}
        return [score(q["required_groups"], q["relevant"],
                      [keys[hit.memory.id] for hit in store.search(
                          q["query"], limit=DEPTH, record_access=False)])
                for q in queries]


def make_embedder(name: str):
    if name == "minilm":
        from dynmemory import SentenceTransformerEmbedder
        return CachedEmbedder(SentenceTransformerEmbedder())
    return CachedEmbedder(NGramHashEmbedder())


def canary(days: list, questions: list) -> dict:
    suite, probes = CONTROL.prepare_control(days, questions)
    return CONTROL.score_control(suite, probes, "token-only")


def run_topic(job: tuple) -> dict:
    """Every configuration for one topic, its shuffle control and, unless given, its canary."""
    root, topic, limit, hybrid, run_canary = job
    days, questions = read_topic_files(root, topic)
    questions = questions[:limit] if limit else questions
    suite = topic_memories(days, questions)
    source = TOPICS[(TOPICS.index(topic) - 1) % len(TOPICS)]
    other_days, other_questions = read_topic_files(root, source)
    other = topic_memories(other_days, other_questions[:limit] if limit else other_questions)
    embedder = make_embedder(hybrid)
    result = {"topic": topic, "messages": len(suite["memories"]), "questions": describe(suite),
              "oracle": oracle(suite), "shuffled_from": source,
              "shuffled_questions": describe(other),
              "shuffled": search_rows(suite, other["queries"], False, None),
              "configs": {name: search_rows(suite, suite["queries"], links,
                                            embedder if name.startswith("hybrid") else None)
                          for name, links in CONFIGS}}
    if run_canary:
        result["canary"] = canary(days, questions)
    print(f"Topic {topic} done", file=sys.stderr, flush=True)
    return result


def mean(values: list):
    values = [v for v in values if v is not None]
    return sum(values) / len(values) if values else None


def accepted_control(path: Path, topics: list, limit) -> dict:
    """A recorded canary report counts only if it matches these inputs and this code."""
    report = json.loads(path.read_text(encoding="utf-8"))
    hashes = {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in report["code_sha256"]}
    reasons = [r for r, bad in (
        ("rule is not token-only", report.get("rule") != "token-only"),
        ("a fault was injected", report.get("fault") is not None),
        ("topics differ", sorted(report.get("topics_run", [])) != sorted(topics)),
        ("code changed since the control", hashes != report["code_sha256"]),
        ("smoke subsets need their own control", limit is not None),
    ) if bad]
    return {"source": str(path), "passed": bool(report.get("passed")) and not reasons,
            "reasons": reasons}


def controls(topics: list, canary_result: dict) -> dict:
    eligible = [s for t in topics for s, d in zip(t["oracle"], t["questions"]) if d["groups"] <= DEPTH]
    shuffled = [s for t in topics for s, d in zip(t["shuffled"], t["shuffled_questions"])
                if d["groups"] <= DEPTH]
    shuffle_all = mean([s["all_required"] for s in shuffled])
    shuffle_cov = mean([s["group_coverage"] for s in shuffled])
    return {
        "C0": {"passed": canary_result["passed"], **canary_result},
        "C1": {"passed": bool(eligible) and all(s["all_required"] == 1.0 for s in eligible),
               "eligible": len(eligible)},
        "C2": {"passed": shuffle_all is not None and shuffle_all <= SHUFFLE_ALL_REQUIRED
               and shuffle_cov <= SHUFFLE_COVERAGE,
               "all_required": shuffle_all, "group_coverage": shuffle_cov, "questions": len(shuffled)},
    }


def paired(topics: list, after: str, before: str, field: str = "all_required", where=None) -> dict:
    changes = [a[field] - b[field] for t in topics
               for a, b, d in zip(t["configs"][after], t["configs"][before], t["questions"])
               if a[field] is not None and b[field] is not None and (where is None or where(d))]
    return STATS.paired_changes(changes) if changes else None


def holm(pvalues: dict) -> dict:
    ordered = sorted(pvalues, key=pvalues.get)
    adjusted, running = {}, 0.0
    for rank, name in enumerate(ordered):
        running = max(running, min(1.0, (len(ordered) - rank) * pvalues[name]))
        adjusted[name] = running
    return adjusted


def decide(control: dict, readings: dict) -> dict:
    failed = [name for name in ("C0", "C1", "C2") if not control[name]["passed"]]
    if failed:
        return {"verdict": "inconclusive (control {} failed)".format(", ".join(failed)),
                "readings": {}}
    if not readings:
        return {"verdict": "no eligible questions", "readings": {}}
    adjusted = holm({name: r["p"] for name, r in readings.items()})
    verdicts = {}
    for name, result in readings.items():
        significant = adjusted[name] < FAMILY_ALPHA and result["mean"] != 0
        verdicts[name] = ("helps" if result["mean"] > 0 else "hurts") if significant \
            else "no clear effect"
    return {"verdict": "; ".join(f"{name}: {v}" for name, v in verdicts.items()),
            "readings": verdicts, "holm_adjusted_p": adjusted}


def tables(topics: list) -> dict:
    rows = [(d, {name: t["configs"][name][i] for name, _ in CONFIGS})
            for t in topics for i, d in enumerate(t["questions"])]
    out = {}
    for label, key in (("cohort", "cohort"), ("type", "type"), ("span", "span")):
        out[label] = {}
        for value in sorted({d[key] for d, _ in rows}):
            chosen = [m for d, m in rows if d[key] == value]
            out[label][value] = {"n": len(chosen), **{
                name: {f: mean([m[name][f] for m in chosen])
                       for f in ("all_required", "group_coverage", "rr")}
                for name, _ in CONFIGS}}
    return out


def analyse(topics: list, canary_result: dict) -> dict:
    control = controls(topics, canary_result)
    readings = {"A_hybrid_vs_lexical": paired(topics, "hybrid", "lexical"),
                "B_links_vs_none": paired(topics, "lexical+links", "lexical")}
    readings = {k: v for k, v in readings.items() if v is not None}
    by_cohort = {c: {"A": paired(topics, "hybrid", "lexical", where=lambda d, c=c: d["cohort"] == c),
                     "B": paired(topics, "lexical+links", "lexical",
                                 where=lambda d, c=c: d["cohort"] == c)}
                 for c in COHORTS[:3]}
    return {"controls": control, "readings": readings, "decision": decide(control, readings),
            "tables": tables(topics), "cohort_changes": by_cohort}


def fmt(value) -> str:
    return "-" if value is None else f"{value:.3f}"


def render(report: dict) -> str:
    a = report["analysis"]
    lines = ["# EverMemBench retrieval", "", f"**Status: {report['status']}.**", "",
             f"Verdict: **{a['decision']['verdict']}**", "",
             "| Control | Passed | Detail |", "| --- | --- | --- |"]
    c = a["controls"]
    lines += [f"| C0 canary | {c['C0']['passed']} | {c['C0'].get('source', 'run here')} "
              f"{'; '.join(c['C0'].get('reasons', []))} |",
              f"| C1 oracle | {c['C1']['passed']} | {c['C1']['eligible']} eligible questions |",
              f"| C2 shuffled | {c['C2']['passed']} | all-required {fmt(c['C2']['all_required'])}, "
              f"coverage {fmt(c['C2']['group_coverage'])} over {c['C2']['questions']} |", "",
              "| Reading | Questions | Mean change | 95% interval | p | Holm p |",
              "| --- | ---: | ---: | --- | ---: | ---: |"]
    for name, r in a["readings"].items():
        adj = a["decision"].get("holm_adjusted_p", {}).get(name)
        lines.append(f"| {name} | {r['questions']} | {r['mean']:+.3f} | "
                     f"[{r['ci95'][0]:+.3f}, {r['ci95'][1]:+.3f}] | {r['p']:.4f} | {fmt(adj)} |")
    for label, table in a["tables"].items():
        lines += ["", f"By {label} (all-required / coverage / RR per configuration):", "",
                  "| " + label + " | n | " + " | ".join(n for n, _ in CONFIGS) + " |",
                  "| --- | ---: |" + " --- |" * len(CONFIGS)]
        for value, row in table.items():
            lines.append(f"| {value} | {row['n']} | " + " | ".join(
                "{} / {} / {}".format(fmt(row[n]["all_required"]), fmt(row[n]["group_coverage"]),
                                      fmt(row[n]["rr"])) for n, _ in CONFIGS) + " |")
    lines += ["", f"Dataset {report['dataset']} at `{report['revision']}`; hybrid `{report['hybrid']}`; "
              f"Python {report['python']}. Draft dated {DRAFT_DATE}; see the script's docstring.", ""]
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--output", type=Path, help="JSON report; Markdown is written beside it")
    parser.add_argument("--approved", action="store_true",
                        help="the researcher approved the decision rule; required for a recorded run")
    parser.add_argument("--smoke", action="store_true",
                        help=f"first {SMOKE_QUESTIONS} questions of one topic; never recorded")
    parser.add_argument("--topic", action="append", choices=TOPICS)
    parser.add_argument("--hybrid", choices=("ngram", "minilm"), default="ngram")
    parser.add_argument("--control-report", type=Path)
    parser.add_argument("--workers", type=int, choices=range(1, 6), default=1)
    args = parser.parse_args(argv)
    results = (ROOT / "experiments" / "results").resolve()
    if not args.smoke and not args.approved:
        print("refusing: the decision rule is a draft; pass --approved once the researcher has "
              "approved it, or --smoke for a check run", file=sys.stderr)
        return 2
    if args.smoke:
        if args.output is None or results in args.output.resolve().parents:
            print("refusing: a smoke run needs --output outside experiments/results", file=sys.stderr)
            return 2
        topics = args.topic or ["01"]
        limit = SMOKE_QUESTIONS
    else:
        topics = args.topic or list(TOPICS)
        limit = None
    output = args.output or results / "evermembench_retrieval.json"
    hashes = {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in SOURCES}
    given = accepted_control(args.control_report, topics, limit) if args.control_report else None
    jobs = [(args.data, topic, limit, args.hybrid, given is None) for topic in topics]
    if args.workers == 1:
        rows = list(map(run_topic, jobs))
    else:
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            rows = list(pool.map(run_topic, jobs))
    for path, digest in hashes.items():
        if digest != hashlib.sha256((ROOT / path).read_bytes()).hexdigest():
            raise RuntimeError(f"source file changed during run: {path}")
    if given is None:
        canaries = [row.pop("canary") for row in rows]
        given = {"source": "run here", "reasons": [],
                 "passed": all(c["all_required_at_10"] == 1.0 and c["unplanted_token_hits"] == 0
                               for c in canaries), "topics": canaries}
    report = {
        "status": "SMOKE, not a recorded run" if args.smoke else f"approved run of the {DRAFT_DATE} draft",
        "dataset": DATASET, "revision": REVISION, "hybrid": args.hybrid, "topics_run": topics,
        "question_limit": limit, "python": platform.python_version(), "code_sha256": hashes,
        "input_sha256": {f"{t}/{n}": d for t in topics
                         for n, d in zip(("dialogue.json", f"qa_{t}.json"), FILE_HASHES[t])},
        "analysis": analyse(rows, given), "topics": rows,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    output.with_suffix(".md").write_text(render(report), encoding="utf-8")
    print(render(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
