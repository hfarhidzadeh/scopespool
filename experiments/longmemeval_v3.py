"""LongMemEval knowledge updates, version 3: all required evidence, not the first piece.

Status: provisional. The v3 annotations were derived from AI labels and an AI review;
the researcher has since made five category decisions and supplied a source-evidence
review (see Runs below and ``dynmemory.longmemeval_v3``), but most annotations are
still not human-adjudicated. The numbers describe that annotation, not settled
ground truth, and they are not comparable with versions 1 and 2, whose cohorts,
update edges and metric differed.

What changed. Versions 1 and 2 took the order of the evidence turns as the
order of replacement and scored a question by its *first* relevant hit. Version 3
(a) gives every question its required evidence as groups of turns, all of which
must be found (a group is satisfied by any one of its turns), and (b) applies as
updates only the supersession edges marked ``supersedes``: additions and separate
events are never archived. The new measure is ``all required@10``: the share of
questions for which every required group has a turn in the top 10. For a
question with one group it equals ``first hit@10``; for a question that needs two
pieces it is stricter, and the gap is what the old metric overstated.

Data. LongMemEval_S (cleaned), restricted to questions included by the selected
annotation file. One store per question, its memories the user's turns, its
links each turn ``related_to`` the next in its session. Cohorts follow the
selected annotation's categories.

Configurations. Embedder: lexical, or MiniLM hybrid (``all-MiniLM-L6-v2``, default
similarity floor 0.3). Updates: kept (every turn stays searchable) or applied (the
v3 ``supersedes`` edges archive the older turn). Retrieval depth 10, no
``record_access``. Links are always the session links.

Measures per question: first hit@10 (any required turn), all required@10, group
coverage@10 (share of groups with a turn in the top 10), reciprocal rank of the
first required turn, and stale-first (an outdated turn ranks above a required
one; only for current questions, whose superseded turns are not required).

Questions and readings. Each is a paired per-question change in
``all required@10`` with its mean, a 95% paired bootstrap interval (10,000
resamples) and a two-sided sign-flip test (exact up to 16 non-zero changes,
otherwise 100,000 flips).
  A. Does applying the supersession edges help questions that ask for the
     current value? current cohort, applied minus kept, per embedder.
  B. Does it hurt questions that need the older evidence? previous and both
     questions with a ``supersedes`` edge, applied minus kept, per embedder.
  C. Does the semantic embedder help? MiniLM minus lexical, updates kept, over
     all 68 questions, and for the questions needing two pieces (both).
Also reported: the "both" cohort's first hit@10 against all required@10; and,
outside the verdict, the change in reciprocal rank (A') and in the share of
questions where an outdated turn ranks first (stale-first) when supersession is
applied to the current-value questions. A' was added after a smoke run on the
hash embedder showed all required@10 at ceiling for that cohort (0.957 before
and after), before any recorded run; the decision rule is unchanged.

Controls, fixed before running (a failed control makes the run inconclusive).
  C1 (negative): a question with no ``supersedes`` edge has identical rows
     whether updates are applied or kept, in both embedders.
  C2 (positive): archiving every required turn (an update whose old turn is each
     required turn) takes all required@10 to 0 for every question, applied.
  C3 (negative): archiving as many random non-required turns as the question has
     edges (5 seeds) moves the mean all required@10 by less than 0.02.
  C2 and C3 supersede through one unrelated placeholder memory appended to the
  set ("zzzarchiver placeholder memory"), so they work whatever the position of
  the turns they archive. A first version used the last non-required memory and
  could not archive a required turn that was itself last; the unit tests found it.

Decision rule, fixed before running. Readings are reported per embedder.
  A "helps" if the mean change is above 0 with p < 0.05 in that embedder;
  B "hurts" if the mean change is below 0 with p < 0.05 in that embedder;
  C "better" or "worse" if the mean change is nonzero with p < 0.05.
  Otherwise "no clear effect". With only 6 questions needing two pieces, the
  "both" figures are descriptive.

Sensitivity. The five questions whose labels were originally contested (2133c1b5,
cf22b7bf, 5c40ec5b, 26bdc477, 42ec0761: three recommended by the first AI
review and two more proposed in an AI-filled sheet) are omitted and every
reading is recomputed. Later category acceptance is recorded in the selected
annotation file.

Runs.
  Run 1 (reports in ``experiments/results/longmemeval_v3_run1_superseded/``):
  ``eval/longmemeval_knowledge_update_annotations_v3.json``, derived from the AI labels
  and the AI review, with the review's three category changes applied.
  Run 2 (this file's default): ``eval/longmemeval_knowledge_update_annotations_v3_reviewed.json``,
  which applies the researcher's five category decisions (2133c1b5 excluded;
  5c40ec5b, cf22b7bf, 26bdc477, 42ec0761 context) and a source-evidence review of the
  questions that need evidence marked as superseded and of the flagged rows (which
  changed the supersession relation of 50635ada, 0ddfec37 and dfde3500 and the required
  groups of c6853660). The file does not record who made the second part of the review;
  it was supplied by the researcher for this run. The design, controls, decision rule and
  statistics are those of run 1; only the annotations changed. The sensitivity run below
  now drops rows whose category was contested before, so it shows how much the
  contested rows matter whatever their final category.
  Later runs can pass a different annotation file and output stem explicitly;
  the report records their annotation path and hash.

Run from the project root (the MiniLM backend needs the venv in
``memory/embedding-environment.md``):

    HF_HUB_OFFLINE=1 python3 -I experiments/longmemeval_v3.py
    python3 -I experiments/longmemeval_v3.py --semantic ngram   # no torch needed
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from dynmemory import NGramHashEmbedder, SentenceTransformerEmbedder  # noqa: E402
from dynmemory.evaluation import CachedEmbedder, query_rows  # noqa: E402
from dynmemory.longmemeval_v3 import convert, load_annotations  # noqa: E402

DATA = ROOT / "data" / "longmemeval" / "longmemeval_s_cleaned.json"
ANNOTATIONS = ROOT / "eval" / "longmemeval_knowledge_update_annotations_v3_reviewed.json"
DEPTH = 10
CONTESTED = ("2133c1b5", "cf22b7bf", "5c40ec5b", "26bdc477", "42ec0761")
CONTROL_SEEDS = 5
C3_LIMIT = 0.02
ALPHA = 0.05
EMBEDDERS = ("lexical", "semantic")
METRICS = ("first_hit", "all_required", "group_coverage", "rr")


def _load_stats():
    spec = importlib.util.spec_from_file_location(
        "ku_stats", ROOT / "experiments" / "longmemeval_knowledge_update.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


STATS = _load_stats()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def annotation_review(path: Path) -> str:
    """Describe the selected annotation's recorded approval scope."""
    approval = json.loads(path.read_text(encoding="utf-8")).get("review", {}).get("category_approval")
    if approval:
        return ("The project owner accepted {} proposed category decisions on {}; remaining"
                " required-evidence groups and update relations are provisional and partly AI-derived."
                " Not comparable with versions 1 and 2.").format(
                    len(approval["decisions"]), approval["date"])
    return ("Annotations are provisional; see the selected file's review metadata for category"
            " decisions. Required-evidence groups and update relations remain partly AI-derived."
            " Not comparable with versions 1 and 2.")


def with_updates(eval_set: dict, updates: list) -> dict:
    return dict(eval_set, updates=updates)


def per_query(rows: list) -> list:
    out = []
    for row in rows:
        relevant = set(row["relevant"])
        out.append({
            "set": row["set"], "tags": row["tags"],
            "first_hit": 1.0 if relevant.intersection(row["retrieved"]) else 0.0,
            "all_required": 1.0 if row["all_required"] else 0.0,
            "group_coverage": row["group_coverage"], "rr": row["reciprocal_rank"],
            "stale_first": row["stale_first"],
        })
    return out


def evaluate(eval_sets: list, embedder, apply_updates: bool) -> list:
    return per_query(query_rows(
        eval_sets, k=DEPTH, links_for=lambda s: s["links"],
        embedder_for=lambda s: embedder, apply_updates=apply_updates))


def category_of(eval_set: dict) -> str:
    return eval_set["queries"][0]["tags"][-1]


def has_supersession(eval_set: dict) -> bool:
    return bool(eval_set.get("updates"))


ARCHIVER = "__v3_archiver__"


def with_archiver(eval_set: dict) -> dict:
    """The set plus one unrelated memory at the end, for controls to supersede through."""
    memories = dict(eval_set["memories"])
    memories[ARCHIVER] = {"content": "zzzarchiver placeholder memory", "kind": "episode"}
    return dict(eval_set, memories=memories)


def archive_required(eval_set: dict) -> dict:
    required = {k for g in eval_set["queries"][0]["required_groups"] for k in g}
    base = with_archiver(eval_set)
    return with_updates(base, [{"old": key, "new": ARCHIVER} for key in sorted(required)])


def archive_random(eval_set: dict, seed: int) -> dict:
    required = {k for g in eval_set["queries"][0]["required_groups"] for k in g}
    pool = [key for key in eval_set["memories"] if key not in required]
    rng = random.Random("v3-c3-{}-{}".format(eval_set["id"], seed))
    count = min(max(1, len(eval_set.get("updates", []))), len(pool))
    base = with_archiver(eval_set)
    return with_updates(base, [{"old": key, "new": ARCHIVER} for key in rng.sample(pool, count)])


def mean(values: list) -> float:
    return sum(values) / len(values) if values else float("nan")


def cohort_table(rows: list, ids: set) -> dict:
    table = {}
    for name in ("current", "previous", "both", "latest_event", "context", "all"):
        chosen = [r for r in rows if r["set"] in ids and (name == "all" or r["tags"][-1] == name)]
        if not chosen:
            continue
        stale = [r["stale_first"] for r in chosen if r["stale_first"] is not None]
        table[name] = {"n": len(chosen), **{m: mean([r[m] for r in chosen]) for m in METRICS},
                       "stale_first": mean(stale) if stale else None}
    return table


def change(after: list, before: list, ids: set, field="all_required") -> dict:
    pairs = [(a, b) for a, b in zip(after, before)
             if a["set"] in ids and a[field] is not None and b[field] is not None]
    if not pairs:
        return None
    return STATS.paired_changes([float(a[field]) - float(b[field]) for a, b in pairs])


def reading(result, direction: str) -> str:
    if result is None:
        return "no questions"
    significant = result["p"] < ALPHA and result["mean"] != 0
    if not significant:
        return "no clear effect"
    positive = result["mean"] > 0
    if direction == "A":
        return "helps" if positive else "hurts"
    if direction == "B":
        return "hurts" if not positive else "helps"
    return "better" if positive else "worse"


def run_all(eval_sets: list, semantic) -> dict:
    embedders = {"lexical": None, "semantic": semantic}
    rows = {(e, u): evaluate(eval_sets, emb, u == "applied")
            for e, emb in embedders.items() for u in ("kept", "applied")}
    controls = {"c1_unchanged": True, "c2_zero": True, "c3_shift": 0.0, "c3_detail": {}}
    no_edge = {s["id"] for s in eval_sets if not has_supersession(s)}
    for e in EMBEDDERS:
        for a, b in zip(rows[(e, "applied")], rows[(e, "kept")]):
            if a["set"] in no_edge and a != b:
                controls["c1_unchanged"] = False
    archived = [archive_required(s) for s in eval_sets]
    for e, emb in embedders.items():
        zero = evaluate(archived, emb, True)
        if any(r["all_required"] for r in zero):
            controls["c2_zero"] = False
        shifts = []
        for seed in range(CONTROL_SEEDS):
            randomised = evaluate([archive_random(s, seed) for s in eval_sets], emb, True)
            shifts.append(abs(mean([r["all_required"] for r in randomised])
                              - mean([r["all_required"] for r in rows[(e, "kept")]])))
        controls["c3_detail"][e] = mean(shifts)
    controls["c3_shift"] = max(controls["c3_detail"].values())
    return {"rows": rows, "controls": controls}


def readings(eval_sets: list, rows: dict, drop: set) -> dict:
    meta = {s["id"]: s for s in eval_sets}
    ids = {i for i in meta if i not in drop}
    cur = {i for i in ids if category_of(meta[i]) == "current"}
    need_old = {i for i in ids if category_of(meta[i]) in ("previous", "both")
                and has_supersession(meta[i])}
    both = {i for i in ids if category_of(meta[i]) == "both"}
    out = {"questions": len(ids), "tables": {}, "A": {}, "B": {}, "C": {}, "C_both": {},
           "A_rr": {}, "A_stale": {}}
    for key, value in rows.items():
        out["tables"]["{}/{}".format(*key)] = cohort_table(value, ids)
    for e in EMBEDDERS:
        out["A"][e] = change(rows[(e, "applied")], rows[(e, "kept")], cur)
        out["B"][e] = change(rows[(e, "applied")], rows[(e, "kept")], need_old)
        out["A_rr"][e] = change(rows[(e, "applied")], rows[(e, "kept")], cur, "rr")
        out["A_stale"][e] = change(rows[(e, "applied")], rows[(e, "kept")], cur, "stale_first")
    out["C"] = change(rows[("semantic", "kept")], rows[("lexical", "kept")], ids)
    out["C_both"] = change(rows[("semantic", "kept")], rows[("lexical", "kept")], both)
    out["sizes"] = {"current": len(cur), "need_old": len(need_old), "both": len(both)}
    return out


def decide(controls: dict, main: dict) -> dict:
    failed = []
    if not controls["c1_unchanged"]:
        failed.append("C1")
    if not controls["c2_zero"]:
        failed.append("C2")
    if controls["c3_shift"] >= C3_LIMIT:
        failed.append("C3")
    verdict = {"failed_controls": failed}
    if failed:
        verdict["verdict"] = "inconclusive (control {} failed)".format(", ".join(failed))
        return verdict
    parts = []
    for e in EMBEDDERS:
        parts.append("{}: applying supersession, current-value questions: {}; questions that need "
                     "the old evidence: {}".format(e, reading(main["A"][e], "A"),
                                                   reading(main["B"][e], "B")))
    parts.append("semantic vs lexical: {}".format(reading(main["C"], "C")))
    verdict["verdict"] = "; ".join(parts)
    return verdict


def fmt(result) -> str:
    if result is None:
        return "-"
    return "{:+.3f} (95% {:+.3f} to {:+.3f}, p {:.3f}; {} better, {} worse, {} same, n {})".format(
        result["mean"], result["ci95"][0], result["ci95"][1], result["p"],
        result["better"], result["worse"], result["same"], result["questions"])


def table_lines(tables: dict) -> list:
    lines = ["| Configuration | Cohort | n | first hit@10 | all required@10 | group coverage | RR | stale first |",
             "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    for name, cohorts in tables.items():
        for cohort, v in cohorts.items():
            lines.append("| {} | {} | {} | {:.3f} | {:.3f} | {:.3f} | {:.3f} | {} |".format(
                name, cohort, v["n"], v["first_hit"], v["all_required"], v["group_coverage"], v["rr"],
                "-" if v["stale_first"] is None else "{:.3f}".format(v["stale_first"])))
    return lines


def render(report: dict) -> str:
    c, m, s = report["controls"], report["main"], report["sensitivity"]
    lines = [
        "# LongMemEval knowledge updates, version 3 (provisional)", "",
        "Real LongMemEval text; no LLM. {} questions annotated for required evidence"
        " and supersession; semantic backend: {}.".format(m["questions"], report["semantic"]),
        report["annotation_review"],
        "Annotations: `{}`. Data sha256 {}; annotations sha256 {}.".format(
            report["annotations"], report["data_sha256"][:16], report["annotations_sha256"][:16]),
        "See the docstring of `experiments/longmemeval_v3.py` for the design and decision rule.", "",
        "## Controls", "",
        "- C1 (no supersession edge: applying updates changes nothing): {}".format(c["c1_unchanged"]),
        "- C2 (archiving every required turn takes all required@10 to 0): {}".format(c["c2_zero"]),
        "- C3 (archiving random non-required turns moves the mean by less than {}): {} (shift: {})".format(
            C3_LIMIT, c["c3_shift"] < C3_LIMIT,
            ", ".join("{} {:.4f}".format(k, v) for k, v in c["c3_detail"].items())), "",
        "**Verdict: {}**".format(report["decision"]["verdict"]), "",
        "## Readings (change in all required@10)", "",
        "- A. Applying supersession to the {} current-value questions, lexical: {}".format(m["sizes"]["current"], fmt(m["A"]["lexical"])),
        "- A. Same, semantic: {}".format(fmt(m["A"]["semantic"])),
        "- A' (not in the verdict), reciprocal rank on the current-value questions: lexical {}; semantic {}".format(
            fmt(m["A_rr"]["lexical"]), fmt(m["A_rr"]["semantic"])),
        "- A' (not in the verdict), stale-first on the current-value questions: lexical {}; semantic {}".format(
            fmt(m["A_stale"]["lexical"]), fmt(m["A_stale"]["semantic"])),
        "- B. Applying supersession to the {} questions that need the old evidence, lexical: {}".format(m["sizes"]["need_old"], fmt(m["B"]["lexical"])),
        "- B. Same, semantic: {}".format(fmt(m["B"]["semantic"])),
        "- C. Semantic minus lexical, updates kept, all {} questions: {}".format(m["questions"], fmt(m["C"])),
        "- C. Same, the {} questions needing two pieces: {}".format(m["sizes"]["both"], fmt(m["C_both"])), "",
        "## Cohorts (depth 10)", ""] + table_lines(m["tables"]) + [
        "", "## Sensitivity: the five originally disputed IDs omitted ({} questions)".format(s["questions"]), "",
        "- A, lexical: {}; semantic: {}".format(fmt(s["A"]["lexical"]), fmt(s["A"]["semantic"])),
        "- B, lexical: {}; semantic: {}".format(fmt(s["B"]["lexical"]), fmt(s["B"]["semantic"])),
        "- C: {}".format(fmt(s["C"])), "",
        "Limits: the annotations are provisional and only {} questions need two pieces of evidence;"
        " links are session links only; updates are an oracle (perfect detection), so the applied"
        " configuration shows the best case and the harm of archiving needed evidence, not what a"
        " detector would do. The whole-turn archive policy is an experimental intervention.".format(m["sizes"]["both"]), ""]
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data", type=Path, default=DATA)
    parser.add_argument("--annotations", type=Path, default=ANNOTATIONS)
    parser.add_argument("--semantic", choices=["sentence-transformers", "ngram"],
                        default="sentence-transformers")
    parser.add_argument("--output", type=Path,
                        default=ROOT / "experiments" / "results" / "longmemeval_v3")
    arguments = parser.parse_args(argv)
    annotations = load_annotations(arguments.annotations)
    questions = json.loads(arguments.data.read_text(encoding="utf-8"))
    eval_sets, _ = convert(questions, annotations)
    del questions
    base = (SentenceTransformerEmbedder() if arguments.semantic == "sentence-transformers"
            else NGramHashEmbedder())
    semantic = CachedEmbedder(base)
    outcome = run_all(eval_sets, semantic)
    main_result = readings(eval_sets, outcome["rows"], set())
    report = {
        "semantic": arguments.semantic, "controls": outcome["controls"], "main": main_result,
        "sensitivity": readings(eval_sets, outcome["rows"], set(CONTESTED)),
        "decision": decide(outcome["controls"], main_result),
        "annotation_review": annotation_review(arguments.annotations),
        "data_sha256": sha256(arguments.data), "annotations_sha256": sha256(arguments.annotations),
        "annotations": str(arguments.annotations.relative_to(ROOT))
        if arguments.annotations.is_relative_to(ROOT) else arguments.annotations.name,
    }
    text = render(report)
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.with_suffix(".json").write_text(json.dumps(report, indent=2) + "\n")
    arguments.output.with_suffix(".md").write_text(text)
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
