"""Build a blind sheet for the human review of the 70 LongMemEval labels.

The labels in ``eval/longmemeval_knowledge_update_labels.json`` were written by
an AI model, and a second AI review (``eval/longmemeval_knowledge_update_label_review.json``)
proposed three category changes and eight evidence or conversion issues. No
human has checked them. This sheet lets the researcher decide each category
from the question and the evidence alone, before seeing either AI verdict.

Design (fixed before the sheet was built):

* One row per labelled question. The reviewer sees the question, its date, the
  benchmark answer and every user turn the benchmark marks as evidence, oldest
  first with its date. Neither AI category, rationale nor note is shown, and
  the rows are shuffled with ``random.Random("labelreview-2026")``.
* Test-retest control: 5 questions, drawn with the same generator, appear a
  second time under a new id, with the evidence listed newest first. A
  reviewer who reads carefully gives the same category both times.
* Categories (the existing schema), one per row in the ``category`` column:
  ``current`` asks for the latest value of something that changed;
  ``previous`` asks for the earlier value; ``both`` needs both versions;
  ``latest_event`` is two separate events that both stay true, and the question
  asks for the most recent; ``context`` means the older turn holds no older
  value of the asked fact; ``exclude`` is a data problem; ``unsure``.
* ``problem`` is optional: ``evidence_incomplete``, ``answer_mismatch``,
  ``order_unclear``, ``future_evidence``, ``not_a_supersession`` or ``other``,
  with detail in ``notes``.

Reading the filled sheet (``--score``):

* The review counts only if at least 4 of the 5 repeated questions got the same
  category both times. Otherwise nothing is concluded from it.
* If it counts, the researcher's category is the label of record. The score
  lists agreement with the original labels and with the AI review's
  recommended categories, and every question where the researcher disagrees
  with either, to be settled by hand. Where the two copies of a repeated
  question differ, the first copy in sheet order is used and the pair is
  flagged.

Usage::

    PYTHONPATH=src python3 experiments/label_review_sheet.py --build
    PYTHONPATH=src python3 experiments/label_review_sheet.py --score FILLED.csv
"""

import argparse
import csv
import json
import random
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "longmemeval" / "longmemeval_s_cleaned.json"
LABELS = ROOT / "eval" / "longmemeval_knowledge_update_labels.json"
LEDGER = ROOT / "eval" / "longmemeval_knowledge_update_label_review.json"
OUT = ROOT / "experiments" / "results" / "label_review"
CATEGORIES = ("current", "previous", "both", "latest_event", "context", "exclude", "unsure")
REPEATS, REPEAT_AGREEMENT, CAP = 5, 4, 1500


def evidence_of(question: dict) -> list:
    """Marked user turns, oldest first: (date, session id, text)."""
    dates = dict(zip(question["haystack_session_ids"], question["haystack_dates"]))
    found = []
    for session_id, session in zip(question["haystack_session_ids"], question["haystack_sessions"]):
        for turn in session:
            if turn.get("has_answer") and turn["role"] == "user":
                found.append((dates[session_id], session_id, turn["content"]))
    return sorted(found, key=lambda item: (item[0], item[1]))


def render_evidence(items: list, newest_first: bool) -> str:
    items = list(reversed(items)) if newest_first else items
    return "\n\n".join(
        "[{}]\n{}".format(date, text if len(text) <= CAP else text[:CAP] + "...")
        for date, _, text in items
    )


def build() -> int:
    labelled = json.loads(LABELS.read_text())["labels"]
    questions = {q["question_id"]: q for q in json.loads(DATA.read_text()) if q["question_id"] in labelled}
    if len(questions) != len(labelled):
        raise SystemExit("labelled questions missing from the data file")
    rng = random.Random("labelreview-2026")
    ids = sorted(questions)
    repeated = rng.sample(ids, REPEATS)
    rows = [(qid, False) for qid in ids] + [(qid, True) for qid in repeated]
    rng.shuffle(rows)
    OUT.mkdir(parents=True, exist_ok=True)
    key = {}
    with open(OUT / "sheet.csv", "w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["id", "question", "question_date", "benchmark_answer", "evidence",
                         "category", "problem", "notes"])
        for number, (qid, again) in enumerate(rows, start=1):
            q = questions[qid]
            row_id = "Q{:02d}".format(number)
            writer.writerow([row_id, q["question"], q["question_date"], q["answer"],
                             render_evidence(evidence_of(q), newest_first=again), "", "", ""])
            key[row_id] = {"question_id": qid, "repeat": again}
    (OUT / "key.json").write_text(json.dumps(key, indent=2) + "\n")
    print("{} rows ({} questions plus {} repeats). Fill the category column of {};"
          " do not open key.json or the AI review files until you are done.".format(
              len(rows), len(ids), REPEATS, OUT / "sheet.csv"))
    return 0


def score(path: Path) -> int:
    key = json.loads((OUT / "key.json").read_text())
    original = {q: v["category"] for q, v in json.loads(LABELS.read_text())["labels"].items()}
    ledger = json.loads(LEDGER.read_text())["reviews"]
    recommended = {q: v["recommended_category"] for q, v in ledger.items()}
    with open(path, newline="") as handle:
        given = {row["id"]: row["category"].strip().lower() for row in csv.DictReader(handle)}
    invalid = [i for i in key if given.get(i) not in CATEGORIES]
    if invalid:
        print("Unlabelled or invalid rows: " + ", ".join(invalid))
        return 1
    by_question = {}
    for row_id in key:  # sheet order
        by_question.setdefault(key[row_id]["question_id"], []).append(given[row_id])
    pairs = {q: c for q, c in by_question.items() if len(c) == 2}
    same = sum(c[0] == c[1] for c in pairs.values())
    valid = same >= REPEAT_AGREEMENT
    print("Repeated questions with the same category both times: {} of {} (need {}): {}".format(
        same, len(pairs), REPEAT_AGREEMENT, "valid" if valid else "NOT valid"))
    for q, c in pairs.items():
        if c[0] != c[1]:
            print("  {} changed: {} then {}".format(q, c[0], c[1]))
    if not valid:
        print("The labels are not consistent enough to conclude anything.")
        return 0
    human = {q: c[0] for q, c in by_question.items()}
    print("Researcher categories: " + ", ".join(
        "{} {}".format(k, v) for k, v in sorted(Counter(human.values()).items())))
    for name, other in (("original labels", original), ("AI review's recommendation", recommended)):
        agree = sum(human[q] == other[q] for q in human)
        print("Agreement with the {}: {} of {}".format(name, agree, len(human)))
    print("Questions where the researcher disagrees with either (to settle by hand):")
    for q in sorted(human):
        if human[q] != original[q] or human[q] != recommended[q]:
            print("  {}: researcher {}, original {}, AI recommendation {}".format(
                q, human[q], original[q], recommended[q]))
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--build", action="store_true")
    group.add_argument("--score", type=Path)
    arguments = parser.parse_args(argv)
    return build() if arguments.build else score(arguments.score)


if __name__ == "__main__":
    raise SystemExit(main())
