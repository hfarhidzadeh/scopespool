"""Compare current-value ranking and historical evidence retrieval on LongMemEval.

This lexical pilot compares keeping all turns, applying annotated whole-turn
supersessions, and moving annotated superseded turns to the end of the full
kept ranking for questions with current intent. Order is preserved within each
group. Historical and unmodified queries use the original kept ranking.

Specify intent with a JSON object mapping each included question ID to current,
history, or unmodified, or explicitly enable the oracle that derives intent
from annotation categories. Both intents and supersession edges are supplied
to the experiment. It measures retrieval policy under those inputs, with no
intent classifier, update detector, or as-of query implementation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sqlite3
import sys
from pathlib import Path
from statistics import mean
from typing import Optional

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from dynmemory.evaluation import MRR_DEPTH, query_rows
from dynmemory.longmemeval_v3 import convert, load_annotations

DEPTH = 10
RR_DEPTH = max(DEPTH, MRR_DEPTH)
DEFAULT_ANNOTATIONS = (
    ROOT / "eval" / "longmemeval_knowledge_update_annotations_v3_category_approved_2026-11-25.json"
)
POLICIES = ("kept", "archive", "demote_current")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def intent_map(eval_sets: list, path: Optional[Path]) -> dict:
    if path is None:
        by_category = {"current": "current", "previous": "history", "both": "history"}
        return {
            item["id"]: by_category.get(item["queries"][0]["tags"][-1], "unmodified")
            for item in eval_sets
        }

    supplied = json.loads(path.read_text(encoding="utf-8"))
    expected = {item["id"] for item in eval_sets}
    if not isinstance(supplied, dict) or set(supplied) != expected:
        raise ValueError("intent file must map exactly the included question IDs")
    if any(value not in ("current", "history", "unmodified") for value in supplied.values()):
        raise ValueError("intent values must be current, history, or unmodified")
    return supplied


def rank(eval_sets: list, *, archive: bool) -> dict:
    # The evaluator's limit bounds its returned ranking. Fetch every lexical or
    # linked candidate before demotion so deeper items can enter the scored top 10.
    limit = max(len(item["memories"]) for item in eval_sets)
    rows = query_rows(
        eval_sets, k=limit, links_for=lambda item: item["links"],
        embedder_for=lambda item: None, apply_updates=archive,
    )
    return {row["set"]: row["retrieved"] for row in rows}


def demote(ranking: list, older: set, intent: str) -> list:
    if intent != "current" or not older:
        return ranking
    return [key for key in ranking if key not in older] + [
        key for key in ranking if key in older
    ]


def score(ranking: list, query: dict) -> dict:
    top = set(ranking[:DEPTH])
    relevant = set(query["relevant"])
    stale = set(query.get("stale", ()))
    first = next((key for key in ranking[:RR_DEPTH] if key in relevant or key in stale), None)
    return {
        "all_required": all(top.intersection(group) for group in query["required_groups"]),
        "rr": next((1.0 / i for i, key in enumerate(ranking[:RR_DEPTH], 1) if key in relevant), 0.0),
        "stale_first": first in stale if stale else None,
    }


def summarize(scores: dict, ids: list) -> dict:
    def rate(metric):
        values = [scores[key][metric] for key in ids if scores[key][metric] is not None]
        return mean(values) if values else None

    return {
        "n": len(ids),
        "all_required": rate("all_required"),
        "rr": rate("rr"),
        "stale_first": rate("stale_first"),
        "stale_n": sum(scores[key]["stale_first"] is not None for key in ids),
    }


def changes(before: dict, after: dict, ids: list) -> dict:
    result = {}
    for metric in ("all_required", "rr", "stale_first"):
        differences = [
            float(after[key][metric]) - float(before[key][metric])
            for key in ids if before[key][metric] is not None
        ]
        result[metric] = {
            "mean_delta": mean(differences) if differences else None,
            "increased": sum(delta > 0 for delta in differences),
            "decreased": sum(delta < 0 for delta in differences),
            "unchanged": sum(delta == 0 for delta in differences),
        }
    return result


def evaluate(eval_sets: list, intents: dict) -> dict:
    queries = {item["id"]: item["queries"][0] for item in eval_sets}
    older = {item["id"]: {edge["old"] for edge in item.get("updates", ())} for item in eval_sets}
    kept = rank(eval_sets, archive=False)
    archived = rank(eval_sets, archive=True)
    demoted = {key: demote(ranking, older[key], intents[key]) for key, ranking in kept.items()}
    ranks = dict(zip(POLICIES, (kept, archived, demoted)))

    controls = {
        "whole_turn_archive_removes_superseded_turns": all(
            older[key].isdisjoint(ranking) for key, ranking in archived.items()
        ),
        "demotion_keeps_all_candidates": all(
            len(ranking) == len(kept[key]) and set(ranking) == set(kept[key])
            for key, ranking in demoted.items()
        ),
        "no_edges_leave_all_rankings_unchanged": all(
            ranking == archived[key] == demoted[key] for key, ranking in kept.items() if not older[key]
        ),
        "demotion_leaves_non_current_rankings_unchanged": all(
            ranking == kept[key] for key, ranking in demoted.items() if intents[key] != "current"
        ),
    }
    groups = {
        "all": list(queries),
        "current intent": [key for key in queries if intents[key] == "current"],
        "history intent": [key for key in queries if intents[key] == "history"],
        "both category": [key for key, query in queries.items() if query["tags"][-1] == "both"],
        "older-required evidence": [
            key for key, query in queries.items() if older[key].intersection(query["relevant"])
        ],
    }
    scores = {
        policy: {key: score(ranking, queries[key]) for key, ranking in policy_ranks.items()}
        for policy, policy_ranks in ranks.items()
    }
    deltas = {
        policy: {
            group: changes(scores["kept"], scores[policy], ids)
            for group, ids in groups.items()
        }
        for policy in ("archive", "demote_current")
    }
    current = deltas["demote_current"]["current intent"]
    older_required = deltas["demote_current"]["older-required evidence"]
    advances = (
        all(controls.values()) and (current["rr"]["mean_delta"] or 0) > 0
        and current["all_required"]["decreased"] == 0
        and older_required["all_required"]["decreased"] == 0
        and bool(groups["older-required evidence"])
    )
    return {
        "controls": controls,
        "cases_changed_by_demotion": sum(kept[key] != demoted[key] for key in kept),
        "cohorts": groups,
        "summary": {
            policy: {group: summarize(scores[policy], ids) for group, ids in groups.items()}
            for policy in POLICIES
        },
        "paired_changes_vs_kept": deltas,
        "advances_to_reviewed_followup": advances,
    }


def render(report: dict) -> str:
    lines = [
        "# History-preserving LongMemEval retrieval pilot",
        "",
        f"This provisional lexical evaluation uses the v3 session links and {report['intent_source']}. "
        "Supersession edges come from the selected annotations.",
        "",
        "Kept searches all turns. Archive applies the annotated whole-turn supersessions. "
        "Demote current moves superseded turns to the end of the full search ranking for "
        "current intent and uses the kept ranking for other intents.",
        "",
        f"| Policy | Cohort | Questions | All required@{DEPTH} | RR@{RR_DEPTH} | Stale-first |",
        "| --- | --- | ---: | ---: | ---: | ---: |",
    ]

    def value(number):
        return "-" if number is None else f"{number:.3f}"

    for policy, cohorts in report["summary"].items():
        label = policy.replace("_", " ")
        for group, stats in cohorts.items():
            stale = value(stats["stale_first"])
            if stats["stale_n"]:
                stale += f" (n={stats['stale_n']})"
            lines.append(
                f"| {label} | {group} | {stats['n']} | {value(stats['all_required'])} "
                f"| {value(stats['rr'])} | {stale} |"
            )
    lines.extend(["", "Stale-first means an outdated turn precedes the first relevant turn "
                  "among answer-related top-10 hits. A stale hit with no relevant hit also counts.",
                  "", "## Checks", ""])
    for control, passed in report["controls"].items():
        lines.append(f"- {control.replace('_', ' ')} — {'pass' if passed else 'fail'}.")
    lines.extend([
        "",
        "Current-intent demotion changed the full ranking for "
        f"{report['cases_changed_by_demotion']} questions.",
        "",
        "The pilot advances to a reviewed follow-up if the controls pass, current-intent "
        "mean RR improves, the older-required cohort is nonempty, and no current-intent or "
        "older-required case loses all-required@10. "
        "The pilot " + ("met" if report["advances_to_reviewed_followup"] else "did not meet")
        + " these criteria.",
        "",
        "The result depends on oracle supersession edges and supplied intent. Evidence "
        "groups and edges remain provisional. The study does not evaluate intent "
        "classification, automated updates, as-of retrieval, or semantic search.",
        "",
        "## Reproduce",
        "",
        "From the repository root, with the cleaned LongMemEval data installed, run:",
        "",
        "```bash",
        "python -I experiments/longmemeval_history_retrieval.py \\",
        f"  --annotations eval/{report['annotations']} \\",
        ("  --intent-file PATH_TO_INTENT_FILE" if "intent_file_sha256" in report
         else "  --oracle-intent-from-annotations"),
        "```",
        "",
        f"- Data SHA-256: `{report['data_sha256']}`",
        f"- Annotation file: `{report['annotations']}`",
        f"- Annotation SHA-256: `{report['annotations_sha256']}`",
        f"- Resolved intent map SHA-256: `{report['intent_sha256']}`",
        f"- Runtime: Python {report['python']}, SQLite {report['sqlite']}",
    ])
    if "intent_file_sha256" in report:
        lines.append(f"- Intent file SHA-256: `{report['intent_file_sha256']}`")
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data", type=Path, default=ROOT / "data/longmemeval/longmemeval_s_cleaned.json")
    parser.add_argument("--annotations", type=Path, default=DEFAULT_ANNOTATIONS)
    intent = parser.add_mutually_exclusive_group(required=True)
    intent.add_argument("--intent-file", type=Path, help="question ID to intent JSON object")
    intent.add_argument("--oracle-intent-from-annotations", action="store_true",
                        help="use provisional v3 categories as oracle intent")
    parser.add_argument("--output", type=Path,
                        default=ROOT / "experiments/results/longmemeval_history_retrieval_pilot")
    args = parser.parse_args(argv)

    annotations = load_annotations(args.annotations)
    questions = json.loads(args.data.read_bytes())
    eval_sets, outcomes = convert(questions, annotations)
    del questions
    if not eval_sets:
        parser.error("no questions converted")
    try:
        intents = intent_map(eval_sets, args.intent_file)
    except ValueError as error:
        parser.error(str(error))

    report = {
        "status": "provisional",
        "intent_source": "an external intent file" if args.intent_file else "oracle intent from annotation categories",
        "oracle_supersession_edges": True,
        "data_sha256": sha256(args.data),
        "annotations": args.annotations.name,
        "annotations_sha256": sha256(args.annotations),
        "intent_sha256": hashlib.sha256(json.dumps(intents, sort_keys=True).encode()).hexdigest(),
        "python": platform.python_version(),
        "sqlite": sqlite3.sqlite_version,
        "conversion_outcomes": dict(outcomes),
        "depth": DEPTH,
        "rr_depth": RR_DEPTH,
        **evaluate(eval_sets, intents),
    }
    if args.intent_file:
        report["intent_file_sha256"] = sha256(args.intent_file)
    markdown = render(report)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.with_suffix(".json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    args.output.with_suffix(".md").write_text(markdown, encoding="utf-8")
    print(markdown, end="")
    return 0 if all(report["controls"].values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
