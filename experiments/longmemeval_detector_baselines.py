"""Update-detector baselines on LongMemEval (version 3, reviewed annotations).

Status: provisional. Ground truth comes from the selected v3 annotation file.
The default reviewed file records five category decisions; a later candidate
records project-owner acceptance of nine proposed category decisions. Other
evidence and update annotations remain partly AI-derived and provisional.
The detectors are the shipped baselines of ``dynmemory.detection`` at their
default settings. This experiment measures them on real conversations.

Question. When a new message arrives, does a baseline detector name the earlier
memory it replaces, and stay quiet when nothing is replaced? And if its decisions
were applied, how much of the oracle's retrieval gain would it recover, and what
would it archive wrongly?

Data. Included annotated knowledge-update questions of LongMemEval_S (cleaned).
One store per question, its memories the user's turns in session order, no links.
For each positive question the *new turn* N is the annotated supersession endpoint;
for a negative it is the first marked turn in the latest evidence session.
Positives are questions whose annotation has a
``supersedes`` edge; the true targets are the old turns of those edges. Negatives
are annotated questions with none (context, separate events, additions): the
right answer is "no update". Control turns are 10 random turns per question that
are not evidence, at least 30 turns into the stream; their fire rate measures
false supersessions on ordinary traffic and is an upper bound, because an
unlabelled genuine update would count as a false fire.

Candidates. When a turn arrives, the system has seen only the turns before it.
Its candidates are the five best BM25 matches for its text among those turns
(a search over the whole store, filtered to earlier turns). This is the same
candidate step for every detector.

Detectors, each given the text and its five candidates, returning an ID or None:
  overlap       ``OverlapUpdateDetector`` (content-word Jaccard, min 0.5)
  hash          ``EmbeddingUpdateDetector`` with ``NGramHashEmbedder`` (threshold 0.6)
  minilm        the same with all-MiniLM-L6-v2 (threshold 0.6)
Controls, which are not candidates for use:
  never         always None
  top           always the best-ranked candidate (fires every time)
  random        a random candidate (expected values are computed exactly)
  oracle-cand   the true old turn if it is among the candidates, else None

Measures. On positives: fired, correct (returns a true target), wrong target,
missed; and candidate recall (a true target is among the five candidates), which
bounds every detector. On negatives and on control turns: fire rate. End to
end: the detector's decision for N (replace the chosen candidate with N) is
applied and retrieval is run on the question with BM25 (depth 10): reciprocal rank
of the first required turn and all required@10, compared with no updates, the
oracle (the annotation's own edges) and random replacement (the same number of
fired questions, a random candidate, averaged over 10 seeds). Only decisions for
N are applied; control-turn decisions are counted but not applied.

Statistics. Paired per-question changes with a 95% bootstrap interval and a
two-sided sign-flip test, as in ``longmemeval_knowledge_update.py``.

Decision rule, fixed before running. Controls:
  C1 ``never`` leaves every retrieval row identical to no updates and fires 0 times.
  C2 ``oracle-cand`` is correct exactly where candidate recall is 1, fires on no
     negative, and its retrieval rows equal the oracle's on those questions.
  A failed control makes the run inconclusive.
A baseline is "usable" only if all of these hold:
  (a) recall on the positives of the current cohort is at least 0.5;
  (b) that recall beats random (expected) with p < 0.05;
  (c) its fire rate on control turns is at most 5%;
  (d) its fire rate on negatives is at most 20%;
  (e) on the current cohort it recovers at least half of the oracle's mean
      reciprocal-rank gain over no updates, and improves on no updates with p < 0.05.
Otherwise it is reported with the conditions it failed. If candidate recall is
under 70% of the old turns, candidate search is the limit and this is reported;
the verdict is unchanged.

Sensitivity (reported, not part of the verdict): each detector over a fixed grid
of thresholds (overlap 0.2 to 0.6; embeddings 0.4 to 0.8). The shipped defaults
are the ones judged.

Run from the project root (the MiniLM backend needs the venv in
``memory/embedding-environment.md``):

    HF_HUB_OFFLINE=1 python3 -I experiments/longmemeval_detector_baselines.py
    python3 -I experiments/longmemeval_detector_baselines.py --semantic ngram
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
from dynmemory.detection import EmbeddingUpdateDetector, OverlapUpdateDetector  # noqa: E402
from dynmemory.evaluation import CachedEmbedder, _build_store, query_rows  # noqa: E402
from dynmemory.longmemeval import question_memories  # noqa: E402
from dynmemory.longmemeval_v3 import convert, load_annotations  # noqa: E402

DATA = ROOT / "data" / "longmemeval" / "longmemeval_s_cleaned.json"
ANNOTATIONS = ROOT / "eval" / "longmemeval_knowledge_update_annotations_v3_reviewed.json"
CANDIDATES = 5
CONTROL_TURNS = 10
MIN_POSITION = 30
RANDOM_SEEDS = 10
DEPTH = 10
RECALL_MIN, CONTROL_FIRE_MAX, NEGATIVE_FIRE_MAX = 0.5, 0.05, 0.20
RECOVERY_MIN, CANDIDATE_RECALL_LIMIT, ALPHA = 0.5, 0.70, 0.05
OVERLAP_GRID = (0.2, 0.3, 0.4, 0.5, 0.6)
EMBEDDING_GRID = (0.4, 0.5, 0.6, 0.7, 0.8)
DEFAULT_OVERLAP, DEFAULT_EMBEDDING = 0.5, 0.6
BIG = 100000


def _load_stats():
    spec = importlib.util.spec_from_file_location(
        "ku_stats_detectors", ROOT / "experiments" / "longmemeval_knowledge_update.py")
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
                " required-evidence groups and update relations are provisional and partly AI-derived.").format(
                    len(approval["decisions"]), approval["date"])
    return ("Annotations are provisional; see the selected file's review metadata for category"
            " decisions. Required-evidence groups and update relations remain partly AI-derived.")


def mean(values) -> float:
    values = list(values)
    return sum(values) / len(values) if values else float("nan")


def prepare(question: dict, annotation: dict, eval_set: dict) -> dict:
    """Everything one question needs: store, positions, N, targets, control turns."""
    _, _, evidence = question_memories(question)
    latest = max(rank for rank, _ in evidence)
    edges = [e for e in annotation["supersession"] if e["relation"] == "supersedes"]
    targets = [e["old"] for e in edges]
    endpoints = {e["new"] for e in edges}
    if len(endpoints) > 1:
        raise ValueError("{}: detector baseline requires one new endpoint".format(eval_set["id"]))
    new_key = next(iter(endpoints)) if endpoints else next(key for rank, key in evidence if rank == latest)
    keys = list(eval_set["memories"])
    position = {key: index for index, key in enumerate(keys)}
    if new_key not in position or any(old not in position or position[old] >= position[new_key]
                                      for old in targets):
        raise ValueError("{}: update endpoint or target is missing or out of order".format(eval_set["id"]))
    evidence_keys = {key for _, key in evidence} | {new_key}
    rng = random.Random("detectors-{}".format(eval_set["id"]))
    pool = [k for k in keys if k not in evidence_keys and position[k] >= MIN_POSITION]
    controls = rng.sample(pool, min(CONTROL_TURNS, len(pool)))
    store, ids = _build_store(eval_set, [], None, apply_updates=False)
    return {"id": eval_set["id"], "set": eval_set, "annotation": annotation, "new": new_key,
            "targets": targets, "positive": bool(targets), "position": position,
            "store": store, "ids": ids, "keys": {v: k for k, v in ids.items()},
            "controls": controls, "category": annotation["category"]}


def candidates_for(prepared: dict, key: str) -> list:
    """The five best BM25 matches among the turns before ``key``: (key, memory)."""
    store, position = prepared["store"], prepared["position"]
    text = prepared["set"]["memories"][key]["content"]
    found = []
    for result in store.search(text, limit=BIG, record_access=False):
        other = prepared["keys"][result.memory.id]
        if position[other] < position[key]:
            found.append((other, result.memory))
            if len(found) == CANDIDATES:
                break
    return found


def decide_with(detector, prepared: dict, key: str, cands: list):
    if not cands:
        return None
    text = prepared["set"]["memories"][key]["content"].strip()
    chosen = detector(text, [memory for _, memory in cands])
    return next((k for k, memory in cands if memory.id == chosen), None)


class Never:
    def __call__(self, text, candidates):
        return None


class Top:
    def __call__(self, text, candidates):
        return candidates[0].id if candidates else None


def make_detectors(semantic, overlap=DEFAULT_OVERLAP, embedding=DEFAULT_EMBEDDING) -> dict:
    return {
        "overlap": OverlapUpdateDetector(overlap),
        "hash": EmbeddingUpdateDetector(NGramHashEmbedder(), embedding),
        "minilm": EmbeddingUpdateDetector(semantic, embedding),
    }


def score_detector(name: str, decisions: dict, items: list) -> dict:
    """Detector-level counts from ``decisions``: question id -> {new, controls}."""
    positives = [p for p in items if p["positive"]]
    current = [p for p in positives if p["category"] == "current"]
    negatives = [p for p in items if not p["positive"]]

    def tally(group):
        correct = sum(decisions[p["id"]]["new"] in p["targets"] for p in group)
        fired = sum(decisions[p["id"]]["new"] is not None for p in group)
        return {"n": len(group), "fired": fired, "correct": correct, "wrong": fired - correct,
                "recall": correct / len(group) if group else float("nan")}

    control_calls = [d for p in items for d in decisions[p["id"]]["controls"]]
    return {
        "name": name, "positives": tally(positives), "current": tally(current),
        "negatives": {"n": len(negatives),
                      "fired": sum(decisions[p["id"]]["new"] is not None for p in negatives)},
        "controls": {"n": len(control_calls), "fired": sum(d is not None for d in control_calls)},
    }


def run_detector(detector, items: list) -> dict:
    out = {}
    for p in items:
        out[p["id"]] = {
            "new": decide_with(detector, p, p["new"], p["cands_new"]),
            "controls": [decide_with(detector, p, k, p["cands_controls"][k]) for k in p["controls"]],
        }
    return out


def with_decision(eval_set: dict, key) -> dict:
    updates = [] if key is None else [{"old": key, "new": eval_set["_new"]}]
    return dict(eval_set, updates=updates)


def retrieval(eval_sets: list, apply: bool) -> list:
    return [
        {"set": r["set"], "tag": r["tags"][-1], "rr": r["reciprocal_rank"],
         "all_required": 1.0 if r["all_required"] else 0.0, "stale_first": r["stale_first"]}
        for r in query_rows(eval_sets, k=DEPTH, links_for=lambda s: s["links"],
                            embedder_for=lambda s: None, apply_updates=apply)
    ]


def sets_for(items: list, decisions: dict) -> list:
    return [with_decision(dict(p["set"], _new=p["new"]), decisions[p["id"]]["new"]) for p in items]


def random_rows(items: list) -> list:
    """Random replacement where a candidate exists, averaged over seeds."""
    runs = []
    for seed in range(RANDOM_SEEDS):
        sets = []
        for p in items:
            rng = random.Random("random-{}-{}".format(p["id"], seed))
            cands = p["cands_new"]
            choice = rng.choice(cands)[0] if cands else None
            sets.append(with_decision(dict(p["set"], _new=p["new"]), choice))
        runs.append(retrieval(sets, True))
    merged = []
    for rows in zip(*runs):
        row = dict(rows[0])
        for field in ("rr", "all_required"):
            row[field] = mean(r[field] for r in rows)
        stale = [r["stale_first"] for r in rows if r["stale_first"] is not None]
        row["stale_first"] = mean(stale) if stale else None
        merged.append(row)
    return merged


def expected_random_recall(p: dict) -> float:
    cands = {k for k, _ in p["cands_new"]}
    return len(cands & set(p["targets"])) / CANDIDATES if p["targets"] else 0.0


def changes(a: list, b: list, ids: set, field: str):
    pairs = [(x, y) for x, y in zip(a, b) if x["set"] in ids]
    return STATS.paired_changes([x[field] - y[field] for x, y in pairs]) if pairs else None


def readings(name: str, detections: dict, rows: dict, items: list, random_by_id: dict) -> dict:
    score = score_detector(name, detections, items)
    current = {p["id"] for p in items if p["category"] == "current" and p["positive"]}
    correct = [(1.0 if detections[p["id"]]["new"] in p["targets"] else 0.0)
               for p in items if p["id"] in current]
    expected = [expected_random_recall(p) for p in items if p["id"] in current]
    vs_random = STATS.paired_changes([c - e for c, e in zip(correct, expected)]) if correct else None
    gain = changes(rows[name], rows["none"], current, "rr")
    oracle_gain = changes(rows["oracle"], rows["none"], current, "rr")
    recovery = (gain["mean"] / oracle_gain["mean"]
                if gain and oracle_gain and oracle_gain["mean"] else float("nan"))
    return {"score": score, "vs_random": vs_random, "rr_gain": gain, "oracle_gain": oracle_gain,
            "recovery": recovery}


def conditions(result: dict) -> list:
    score = result["score"]
    failed = []
    if not score["current"]["recall"] >= RECALL_MIN:
        failed.append("a: recall on current positives below {}".format(RECALL_MIN))
    vr = result["vs_random"]
    if not (vr and vr["mean"] > 0 and vr["p"] < ALPHA):
        failed.append("b: does not beat random with p < {}".format(ALPHA))
    controls = score["controls"]
    if controls["n"] and controls["fired"] / controls["n"] > CONTROL_FIRE_MAX:
        failed.append("c: fires on more than {:.0%} of control turns".format(CONTROL_FIRE_MAX))
    negatives = score["negatives"]
    if negatives["n"] and negatives["fired"] / negatives["n"] > NEGATIVE_FIRE_MAX:
        failed.append("d: fires on more than {:.0%} of negatives".format(NEGATIVE_FIRE_MAX))
    gain = result["rr_gain"]
    if not (result["recovery"] >= RECOVERY_MIN and gain and gain["mean"] > 0 and gain["p"] < ALPHA):
        failed.append("e: recovers less than half of the oracle's rank gain, or not significantly")
    return failed


def run_all(items: list, semantic) -> dict:
    for p in items:
        p["cands_new"] = candidates_for(p, p["new"])
        p["cands_controls"] = {k: candidates_for(p, k) for k in p["controls"]}
    detectors = make_detectors(semantic)
    controls = {"never": Never(), "top": Top()}
    detections = {name: run_detector(d, items) for name, d in {**detectors, **controls}.items()}
    detections["oracle-cand"] = {
        p["id"]: {"new": next((k for k, _ in p["cands_new"] if k in p["targets"]), None),
                  "controls": [None] * len(p["controls"])} for p in items}
    rows = {"none": retrieval([p["set"] for p in items], False),
            "oracle": retrieval([p["set"] for p in items], True)}
    for name, decided in detections.items():
        rows[name] = retrieval(sets_for(items, decided), True)
    rows["random"] = random_rows(items)
    ids = [p["id"] for p in items]
    record = {name: readings(name, detections[name], rows, items, None)
              for name in list(detectors) + ["never", "top", "oracle-cand"]}
    candidate_recall = {
        "targets": sum(len(p["targets"]) for p in items if p["positive"]),
        "in_candidates": sum(len({k for k, _ in p["cands_new"]} & set(p["targets"]))
                             for p in items if p["positive"]),
        "questions": sum(bool({k for k, _ in p["cands_new"]} & set(p["targets"]))
                         for p in items if p["positive"]),
        "positives": sum(p["positive"] for p in items)}
    return {"detections": detections, "rows": rows, "readings": record,
            "candidate_recall": candidate_recall, "ids": ids}


def check_controls(items: list, outcome: dict) -> dict:
    none_rows, rows = outcome["rows"]["none"], outcome["rows"]
    c1 = rows["never"] == none_rows and all(
        d["new"] is None and not any(d["controls"]) for d in outcome["detections"]["never"].values())
    oracle_cand = outcome["detections"]["oracle-cand"]
    reached = {p["id"] for p in items if {k for k, _ in p["cands_new"]} & set(p["targets"])}
    c2 = all((oracle_cand[p["id"]]["new"] in p["targets"]) == (p["id"] in reached and p["positive"])
             for p in items)
    c2 = c2 and all(oracle_cand[p["id"]]["new"] is None for p in items if not p["positive"])
    c2 = c2 and all(a == b for a, b, p in zip(rows["oracle-cand"], rows["oracle"], items)
                    if p["id"] in reached and len(p["targets"]) == 1)
    return {"c1_never_is_none": c1, "c2_oracle_candidate": c2}


def sweep(items: list, semantic) -> list:
    table = []
    for kind, grid in (("overlap", OVERLAP_GRID), ("hash", EMBEDDING_GRID), ("minilm", EMBEDDING_GRID)):
        for value in grid:
            detector = make_detectors(semantic, overlap=value, embedding=value)[kind]
            score = score_detector(kind, run_detector(detector, items), items)
            table.append({"detector": kind, "threshold": value,
                          "recall_current": score["current"]["recall"],
                          "wrong_positives": score["positives"]["wrong"],
                          "negatives_fired": score["negatives"]["fired"],
                          "controls_fired": score["controls"]["fired"],
                          "controls_n": score["controls"]["n"]})
    return table


def fmt_changes(result) -> str:
    if result is None:
        return "-"
    return "{:+.3f} (95% {:+.3f} to {:+.3f}, p {:.3f}; {} better, {} worse, n {})".format(
        result["mean"], result["ci95"][0], result["ci95"][1], result["p"],
        result["better"], result["worse"], result["questions"])


def render(report: dict) -> str:
    c, out = report["controls"], report
    cr = report["candidate_recall"]
    lines = [
        "# Update-detector baselines on LongMemEval (version 3, reviewed annotations; provisional)", "",
        "Real LongMemEval text; no LLM. {} questions ({} positives with a `supersedes` edge, {} negatives);"
        " MiniLM backend: {}.".format(report["questions"], cr["positives"], report["questions"] - cr["positives"],
                                      report["semantic"]),
        "Annotations: `{}` (sha256 {}); data sha256 {}.".format(
            report["annotations"], report["annotations_sha256"][:16], report["data_sha256"][:16]),
        report["annotation_review"],
        "See the docstring of `experiments/longmemeval_detector_baselines.py` for the design and rule.", "",
        "## Controls", "",
        "- C1 (`never` equals no updates and fires 0 times): {}".format(c["c1_never_is_none"]),
        "- C2 (`oracle-cand` is right exactly where a true target is a candidate, and matches the oracle there): {}".format(
            c["c2_oracle_candidate"]), "",
        "**Verdict: {}**".format(report["verdict"]), "",
        "Candidate recall (a true old turn among the 5 candidates): {} of {} old turns; {} of {} positive"
        " questions{}.".format(cr["in_candidates"], cr["targets"], cr["questions"], cr["positives"],
                               "; candidate search limits every detector"
                               if cr["targets"] and cr["in_candidates"] / cr["targets"] < CANDIDATE_RECALL_LIMIT else ""),
        "", "## Detectors at their shipped defaults", "",
        "| Detector | Positives: fired / correct / wrong | Current recall | Negatives fired | Control turns fired | Recovery of oracle RR gain | Conditions failed |",
        "| --- | --- | --- | --- | --- | --- | --- |"]
    for name in ("overlap", "hash", "minilm", "top", "never", "oracle-cand"):
        r = out["readings"][name]
        s = r["score"]
        failed = "-" if name in ("top", "never", "oracle-cand") else ("none (usable)" if not r["failed"] else "; ".join(
            f.split(":")[0] for f in r["failed"]))
        lines.append("| {} | {} / {} / {} of {} | {:.3f} ({} of {}) | {} of {} | {} of {} | {} | {} |".format(
            name, s["positives"]["fired"], s["positives"]["correct"], s["positives"]["wrong"], s["positives"]["n"],
            s["current"]["recall"], s["current"]["correct"], s["current"]["n"],
            s["negatives"]["fired"], s["negatives"]["n"], s["controls"]["fired"], s["controls"]["n"],
            "{:.2f}".format(r["recovery"]) if r["recovery"] == r["recovery"] else "-", failed))
    lines += ["", "Condition letters: a recall, b beats random, c control-turn fire rate, d negative fire rate, e recovery.", "",
              "## Recall against random (current positives, correct minus expected-by-chance)", ""]
    for name in ("overlap", "hash", "minilm", "top"):
        lines.append("- {}: {}".format(name, fmt_changes(out["readings"][name]["vs_random"])))
    lines += ["", "## End to end, current cohort (reciprocal rank of the first required turn, depth 10)", "",
              "- Oracle gain over no updates: {}".format(fmt_changes(out["readings"]["overlap"]["oracle_gain"]))]
    for name in ("overlap", "hash", "minilm", "top"):
        lines.append("- {} gain over no updates: {}".format(name, fmt_changes(out["readings"][name]["rr_gain"])))
    lines += ["", "## Retrieval by cohort (mean over questions)", "",
              "| Arm | Cohort | n | RR | all required@10 |", "| --- | --- | --- | --- | --- |"]
    for arm, cohorts in out["tables"].items():
        for cohort, v in cohorts.items():
            lines.append("| {} | {} | {} | {:.3f} | {:.3f} |".format(arm, cohort, v["n"], v["rr"], v["all_required"]))
    lines += ["", "## Threshold sweep (reported, not part of the verdict)", "",
              "| Detector | Threshold | Current recall | Wrong target (positives) | Negatives fired | Control turns fired |",
              "| --- | --- | --- | --- | --- | --- |"]
    for row in out["sweep"]:
        lines.append("| {} | {} | {:.3f} | {} | {} | {} of {} |".format(
            row["detector"], row["threshold"], row["recall_current"], row["wrong_positives"],
            row["negatives_fired"], row["controls_fired"], row["controls_n"]))
    lines += ["", "Limits: the annotations are provisional; candidates come from BM25 over the whole store filtered"
              " to earlier turns; only the decision for the new turn is applied, so control-turn fires are counted"
              " but their harm is not measured; a control-turn fire may be a genuine unlabelled update, so that rate"
              " is an upper bound; baselines are simple by design and a model-based detector is not tested here.", ""]
    return "\n".join(lines)


def tables_for(items: list, rows: dict) -> dict:
    cohort_of = {p["id"]: p["category"] for p in items}
    out = {}
    for arm in ("none", "oracle", "overlap", "hash", "minilm", "top", "random"):
        cohorts = {}
        for name in ("current", "previous", "both", "latest_event", "context", "all"):
            chosen = [r for r in rows[arm] if name == "all" or cohort_of[r["set"]] == name]
            if chosen:
                cohorts[name] = {"n": len(chosen), "rr": mean(r["rr"] for r in chosen),
                                 "all_required": mean(r["all_required"] for r in chosen)}
        out[arm] = cohorts
    return out


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data", type=Path, default=DATA)
    parser.add_argument("--annotations", type=Path, default=ANNOTATIONS)
    parser.add_argument("--semantic", choices=["sentence-transformers", "ngram"],
                        default="sentence-transformers")
    parser.add_argument("--output", type=Path,
                        default=ROOT / "experiments" / "results" / "longmemeval_detector_baselines")
    arguments = parser.parse_args(argv)
    annotations = load_annotations(arguments.annotations)
    questions = json.loads(arguments.data.read_text(encoding="utf-8"))
    eval_sets, _ = convert(questions, annotations)
    wanted = {s["id"]: s for s in eval_sets}
    items = [prepare(q, annotations[q["question_id"]], wanted[q["question_id"]])
             for q in questions if q["question_id"] in wanted]
    del questions
    base = (SentenceTransformerEmbedder() if arguments.semantic == "sentence-transformers"
            else NGramHashEmbedder())
    semantic = CachedEmbedder(base)
    outcome = run_all(items, semantic)
    for name, r in outcome["readings"].items():
        r["failed"] = conditions(r) if name in ("overlap", "hash", "minilm") else []
    controls = check_controls(items, outcome)
    verdict = ("inconclusive (control {} failed)".format(
        ", ".join(k for k, v in controls.items() if not v))
        if not all(controls.values()) else "; ".join(
            "{}: {}".format(n, "usable" if not outcome["readings"][n]["failed"]
                            else "not usable ({})".format(", ".join(f.split(":")[0]
                                                                  for f in outcome["readings"][n]["failed"])))
            for n in ("overlap", "hash", "minilm")))
    report = {
        "semantic": arguments.semantic, "questions": len(items), "controls": controls,
        "verdict": verdict, "readings": outcome["readings"],
        "candidate_recall": outcome["candidate_recall"],
        "tables": tables_for(items, outcome["rows"]), "sweep": sweep(items, semantic),
        "annotations": str(arguments.annotations.relative_to(ROOT))
        if arguments.annotations.is_relative_to(ROOT) else arguments.annotations.name,
        "annotations_sha256": sha256(arguments.annotations), "data_sha256": sha256(arguments.data),
        "annotation_review": annotation_review(arguments.annotations),
    }
    text = render(report)
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.with_suffix(".json").write_text(json.dumps(report, indent=2, default=str) + "\n")
    arguments.output.with_suffix(".md").write_text(text)
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
