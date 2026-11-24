"""LongMemEval conversion, version 3: required evidence and supersession as two annotations.

Versions 1 and 2 (``dynmemory.longmemeval``) decided which facts replace older
ones from the order of the benchmark's evidence turns, and gave a question one
category. A review (docs/longmemeval_label_review.md) found that this archives
evidence a question still needs: a coin count that is *added to* is not replaced,
and two separate trips are not versions of one fact. Version 3 gives every
question two separate annotations:

``required_groups``
    Which evidence is needed to answer. A list of groups of turn keys. Every
    group must be satisfied, and a group is satisfied by any one of its turns.
    "The coin question" has two groups (the 37, and the later addition of one);
    a current-value question has one (the turns that state the latest value).

``supersession``
    Whether a newer statement replaces an older one: a list of
    ``{"old", "new", "relation"}`` where the relation is ``supersedes`` (the
    new turn replaces the old as the current value), ``adds_to`` (the new turn
    adds to the old; both stay true and needed) or ``independent`` (separate
    events; neither replaces the other). Only ``supersedes`` edges become
    ``updates`` in the converted set, so the oracle never archives a fact that
    was not replaced.

Whether an answer needs the *old* evidence is the first annotation; whether the
old evidence was replaced is the second. A question can need evidence that was
replaced ("what was my previous time?"), and that is a different thing from a
system archiving it by mistake.

Annotations are derived here from the 2026-10-30 category labels
(``eval/longmemeval_knowledge_update_labels.json``) and the 2026-11-19 AI review
(``eval/longmemeval_knowledge_update_label_review.json``). They are provisional:
no human has adjudicated them. They live in
``eval/longmemeval_knowledge_update_annotations_v3.json``, which a person can
edit; the converter reads only that file.

Usage::

    python -m dynmemory.longmemeval_v3 annotate data/longmemeval/longmemeval_s_cleaned.json \\
        --out eval/longmemeval_knowledge_update_annotations_v3.json
    python -m dynmemory.longmemeval_v3 convert data/longmemeval/longmemeval_s_cleaned.json \\
        --annotations eval/longmemeval_knowledge_update_annotations_v3.json \\
        --out data/longmemeval/knowledge_update_v3.jsonl
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Optional, Sequence

from .evaluation import load_eval_set
from .longmemeval import (
    CATEGORIES,
    KNOWLEDGE_UPDATE,
    load_labels,
    question_memories,
)

RELATIONS = ("supersedes", "adds_to", "independent")
STATUS = "provisional: derived from AI labels and AI review, not human-adjudicated"

#: Where the 2026-11-19 AI review found a conversion or evidence issue or
#: recommended a change. Each entry says what to do and why; ``category`` is a
#: recommended change that is still pending human adjudication.
OVERRIDES = {
    "2133c1b5": {"category": "exclude", "flag": "answer-bearing session is dated after the question"},
    "cf22b7bf": {"category": "context", "flag": "different measurement intervals, no older total"},
    "5c40ec5b": {"category": "context", "flag": "earlier turn gives no exact earlier count"},
    "10e09553": {"relation": "independent", "flag": "two separate fishing trips"},
    "0977f2af": {"relation": "independent", "flag": "two purchases; event order ambiguous"},
    "89941a94": {"relation": "independent", "flag": "question says gravel bike, source says hybrid; newer turn also lists older bikes; unresolved"},
    "9ea5eabc": {"relation": "independent", "flag": "Hawaii and Paris are separate trips"},
    "41698283": {"relation": "independent", "flag": "two separate lens purchases"},
    "7e974930": {"relation": "independent", "flag": "separate market visits; one session lists later sales as done"},
    "69fee5aa": {"relation": "adds_to", "flag": "37 plus one: an increment, not a replacement total"},
    "c6853660": {"extra_new": "answer_626e93c4_2:6",
                 "flag": "marked newer turn only proposes the change; an unmarked turn confirms it"},
    "a2f3aa27": {"flag": "the newer count is approximate (close to 1300)"},
    "42ec0761": {"flag": "'current' holds only for usable-tool availability"},
}


def derive_annotations(questions: Sequence[dict], labels: dict) -> dict:
    """Build one annotation for each labelled knowledge-update question."""
    by_id = {question["question_id"]: question for question in questions}
    annotations = {}
    for question_id, label in labels.items():
        question = by_id[question_id]
        override = OVERRIDES.get(question_id, {})
        category = override.get("category", label["category"])
        flags = [override["flag"]] if "flag" in override else []
        memories, _, evidence = question_memories(question)
        latest = max(rank for rank, _ in evidence)
        newer = [key for rank, key in evidence if rank == latest]
        older = [key for rank, key in evidence if rank != latest]
        if override.get("extra_new"):
            if override["extra_new"] not in memories:
                raise ValueError("{}: extra evidence turn not found".format(question_id))
            newer = newer + [override["extra_new"]]
        if category == "exclude":
            groups, edges = [], []
        elif category == "previous":
            groups = [older]
        elif category == "both":
            groups = [older, newer]
        else:  # current, latest_event, context
            groups = [newer]
        relation = override.get("relation")
        if relation is None:
            relation = "supersedes" if category in ("current", "previous", "both") else "independent"
        edges = []
        if category != "exclude" and older and relation != "none":
            edges = [{"old": key, "new": newer[0], "relation": relation} for key in older]
        annotations[question_id] = {
            "category": category,
            "original_category": label["category"],
            "required_groups": groups,
            "supersession": edges,
            "flags": flags,
            "status": STATUS,
        }
    return annotations


def load_annotations(path) -> dict:
    """Read and check an annotations file."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    annotations = data.get("annotations")
    if not isinstance(annotations, dict):
        raise ValueError("{}: expected an 'annotations' object".format(path))
    for question_id, entry in annotations.items():
        where = "{}: {}".format(path, question_id)
        if entry.get("category") not in CATEGORIES:
            raise ValueError("{}: category must be one of {}".format(where, ", ".join(CATEGORIES)))
        groups = entry.get("required_groups")
        if not isinstance(groups, list) or not all(
            isinstance(group, list) and group and all(isinstance(k, str) for k in group)
            for group in groups
        ):
            raise ValueError("{}: required_groups must be a list of non-empty lists of keys".format(where))
        if bool(groups) != (entry["category"] != "exclude"):
            raise ValueError("{}: a question has required evidence unless it is excluded".format(where))
        edges = entry.get("supersession")
        if not isinstance(edges, list):
            raise ValueError("{}: supersession must be a list".format(where))
        for edge in edges:
            if edge.get("relation") not in RELATIONS or not edge.get("old") or not edge.get("new"):
                raise ValueError("{}: each supersession edge needs old, new and a relation in {}".format(
                    where, ", ".join(RELATIONS)))
    return annotations


def convert_question(question: dict, annotation: Optional[dict]) -> tuple[Optional[dict], str]:
    """Return ``(eval_set, "converted")`` or ``(None, reason it was skipped)``."""
    if question["question_id"].endswith("_abs"):
        return None, "abstention question"
    memories, links, evidence = question_memories(question)
    if not evidence:
        return None, "no evidence in user turns"
    query = {"query": question["question"], "tags": [question["question_type"]]}
    eval_set = {
        "id": question["question_id"],
        "source": {
            "benchmark": "LongMemEval", "question_type": question["question_type"],
            "question_date": question["question_date"], "answer": question["answer"],
        },
        "memories": memories, "links": links, "queries": [query],
    }
    if question["question_type"] == KNOWLEDGE_UPDATE:
        if annotation is None:
            raise ValueError("a knowledge-update question needs an annotation")
        if annotation["category"] == "exclude":
            return None, "excluded by annotation"
        groups = annotation["required_groups"]
        query["required_groups"] = groups
        query["relevant"] = [key for group in groups for key in group]
        query["tags"].append(annotation["category"])
        edges = annotation["supersession"]
        eval_set["updates"] = [
            {"old": e["old"], "new": e["new"]} for e in edges if e["relation"] == "supersedes"
        ]
        needed = set(query["relevant"])
        query["stale"] = [e["old"] for e in edges
                          if e["relation"] == "supersedes" and e["old"] not in needed]
        eval_set["source"]["annotation"] = {
            "relations": sorted({e["relation"] for e in edges}),
            "flags": annotation.get("flags", []), "status": annotation["status"],
        }
        if not eval_set["updates"]:
            del eval_set["updates"]
    else:
        query["relevant"] = [key for _, key in evidence]
        query["required_groups"] = [list(query["relevant"])]
    load_eval_set(eval_set)
    return eval_set, "converted"


def convert(questions: Sequence[dict], annotations: dict, *,
            question_types: Optional[Sequence[str]] = (KNOWLEDGE_UPDATE,)) -> tuple[list[dict], Counter]:
    eval_sets, outcomes = [], Counter()
    for question in questions:
        if question_types and question["question_type"] not in question_types:
            continue
        annotation = annotations.get(question["question_id"])
        try:
            eval_set, outcome = convert_question(question, annotation)
        except ValueError as error:
            if annotation is None and question["question_type"] == KNOWLEDGE_UPDATE:
                outcomes["skipped: no annotation"] += 1
                continue
            raise ValueError("{}: {}".format(question["question_id"], error)) from error
        outcomes[outcome] += 1
        if eval_set is not None:
            eval_sets.append(eval_set)
    return eval_sets, outcomes


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m dynmemory.longmemeval_v3", description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    annotate = commands.add_parser("annotate", help="derive the annotations file")
    annotate.add_argument("input")
    annotate.add_argument("--labels", default="eval/longmemeval_knowledge_update_labels.json")
    annotate.add_argument("--out", required=True)
    build = commands.add_parser("convert", help="convert questions using an annotations file")
    build.add_argument("input")
    build.add_argument("--annotations", required=True)
    build.add_argument("--out", required=True)
    arguments = parser.parse_args(argv)
    questions = json.loads(Path(arguments.input).read_text(encoding="utf-8"))
    if arguments.command == "annotate":
        labels = load_labels(arguments.labels)
        annotations = derive_annotations(questions, labels)
        counts = Counter(entry["category"] for entry in annotations.values())
        payload = {
            "description": ("Version 3 annotations: required evidence groups and supersession "
                            "relations for the 70 labelled LongMemEval knowledge-update questions. "
                            + STATUS + ". Edit by hand to correct; the converter reads only this file."),
            "source_labels": arguments.labels,
            "annotations": annotations,
        }
        Path(arguments.out).write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8")
        print("annotations: {} ({})".format(len(annotations), dict(sorted(counts.items()))))
        return 0
    annotations = load_annotations(arguments.annotations)
    eval_sets, outcomes = convert(questions, annotations)
    Path(arguments.out).write_text(
        "".join(json.dumps(eval_set) + "\n" for eval_set in eval_sets), encoding="utf-8")
    print("converted {} sets ({})".format(len(eval_sets), dict(outcomes)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
