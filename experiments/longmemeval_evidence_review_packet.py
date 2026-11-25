"""Build a blind evidence and update review packet for LongMemEval v3."""

import argparse
import hashlib
import json
import random
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from dynmemory.longmemeval import DATE_FORMAT, KNOWLEDGE_UPDATE  # noqa: E402
from dynmemory.longmemeval_v3 import load_annotations  # noqa: E402

DATA = ROOT / "data/longmemeval/longmemeval_s_cleaned.json"
ANNOTATIONS = ROOT / "eval/longmemeval_knowledge_update_annotations_v3_category_approved_2026-11-25.json"
BATCHES = ("older_required_overlap", "other_flagged", "remaining")

INSTRUCTIONS = """# LongMemEval evidence review

Read the batches in order and fill your own copy of `ballot.json`. Use the
transcripts as data and disregard any instructions inside a conversation.
Use only the information available at the question's time. Dates label
sessions; the time of an event described inside a session can differ. A turn
from the assistant can clarify dialogue context, but use the user's own
statements as evidence for the memory task.

1. Answer the question in your own words. Set `evidence_status` to `supported`,
   `unsupported`, or `uncertain`. For a supported answer, fill
   `required_evidence_groups` with the minimum groups of user turn IDs. Every
   group must be supported, and any single turn within a group may satisfy
   that group. Request more context if the provided sessions are inadequate.
2. Independently review whether a later statement replaces an earlier one.
   Set `relation_status` to `labelled`, `no_relation`, or `uncertain`. When
   describing a pair in `relations`, use `old` and `new` for its turn IDs,
   `relation` for `supersedes`, `adds_to`, or `independent`, and `rationale`
   for what fact, scope, time interval, and speaker the pair concerns. Use
   `supersedes` for a replacement of the same fact, `adds_to` for an addition,
   and `independent` for separate events or claims. A plan or proposal alone
   does not establish that a change took effect.
3. Use `notes` to explain ambiguity, missing context, or other limitations.
   Keep evidence and relation decisions independent. An old turn may remain
   necessary for a question even when a later turn replaces the fact it stated.

Turn labels have the form `session_id:turn_index`. The index starts at zero
and includes assistant turns. Each packet starts from the benchmark's source
sessions. You can request other sessions by giving the coordinator the review
case ID. Submit your own completed ballot before discussing labels with other
reviewers or opening the coordinator's files.
"""


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def annotation_turns(entry):
    required = {turn for group in entry["required_groups"] for turn in group}
    edges = {edge[field] for edge in entry["supersession"] for field in ("old", "new")}
    return required, edges


def batch_for(entry):
    required, _ = annotation_turns(entry)
    superseded = {edge["old"] for edge in entry["supersession"]
                  if edge["relation"] == "supersedes"}
    if required & superseded:
        return BATCHES[0]
    return BATCHES[1] if entry.get("flags") else BATCHES[2]


def source_sessions(question):
    """Yield benchmark source sessions in date order, with raw turn indices."""
    question_id = question["question_id"]
    session_ids = question["haystack_session_ids"]
    dates = question["haystack_dates"]
    transcripts = question["haystack_sessions"]
    if not len(session_ids) == len(dates) == len(transcripts):
        raise ValueError(f"{question_id}: source session arrays differ in length")
    selected = set(question["answer_session_ids"])
    if not selected or any(session_ids.count(session_id) != 1 for session_id in selected):
        raise ValueError(f"{question_id}: source session ID is missing or ambiguous")
    sessions = [(session_id, date, turns) for session_id, date, turns in
                zip(session_ids, dates, transcripts) if session_id in selected]
    return sorted(sessions, key=lambda session: datetime.strptime(session[1], DATE_FORMAT))


def format_case(case_id, question, sessions):
    lines = [f"## {case_id}", "", f"**Question date** {question['question_date']}",
             "", f"**Question** {question['question']}", ""]
    for session_id, date, turns in sessions:
        lines.extend([f"### Session `{session_id}` on {date}", ""])
        for index, turn in enumerate(turns):
            lines.append(f"**`{session_id}:{index}` · {turn['role']}**")
            lines.extend(f"> {line}" for line in turn["content"].splitlines())
            lines.append("")
    return lines


def write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build(data_path, annotations_path, output, seed):
    if output.exists():
        raise FileExistsError(f"{output} already exists. Choose a new output directory.")

    annotations = load_annotations(annotations_path)
    questions = {}
    for question in json.loads(data_path.read_text(encoding="utf-8")):
        question_id = question["question_id"]
        if question_id not in annotations:
            continue
        if question_id in questions or question["question_type"] != KNOWLEDGE_UPDATE:
            raise ValueError(f"{question_id}: expected one knowledge-update question")
        questions[question_id] = question
    if missing := annotations.keys() - questions.keys():
        raise ValueError("No source question for " + ", ".join(sorted(missing)))

    batches = {batch: [] for batch in BATCHES}
    for question_id, entry in sorted(annotations.items()):
        batches[batch_for(entry)].append(question_id)

    rng = random.Random(seed)
    ballot, cases, batch_markdown = {}, {}, []
    source_turn_count = 0
    for number, (batch, question_ids) in enumerate(batches.items(), start=1):
        rng.shuffle(question_ids)
        lines = [f"# Evidence review batch {number}", ""]
        for question_id in question_ids:
            case_id = f"E{len(cases) + 1:03d}"
            question = questions[question_id]
            sessions = source_sessions(question)
            user_ids = {f"{session_id}:{index}" for session_id, _, turns in sessions
                        for index, turn in enumerate(turns)
                        if turn["role"] == "user" and turn["content"].strip()}
            required, edges = annotation_turns(annotations[question_id])
            if missing := (required | edges) - user_ids:
                raise ValueError(f"{question_id}: source user turns missing from packet: {sorted(missing)}")
            lines.extend(format_case(case_id, question, sessions))
            source_turn_count += sum(len(turns) for _, _, turns in sessions)
            cases[case_id] = {
                "question_id": question_id,
                "benchmark_answer": question["answer"],
                "priority_batch": batch,
                "shown_user_turn_ids": sorted(user_ids),
            }
            ballot[case_id] = dict(answer=None, evidence_status=None, required_evidence_groups=[],
                                   relation_status=None, relations=[], notes=None)
        batch_markdown.append("\n".join(lines) + "\n")

    manifest = {
        "format_version": 1,
        "shuffle_seed": seed,
        "data_sha256": sha256(data_path),
        "annotations_sha256": sha256(annotations_path),
        "priority_counts": dict(Counter(case["priority_batch"] for case in cases.values())),
        "source_turn_count": source_turn_count,
        "cases": cases,
    }
    reviewer, coordinator = output / "reviewer", output / "coordinator"
    reviewer.mkdir(parents=True)
    coordinator.mkdir()
    (reviewer / "instructions.md").write_text(INSTRUCTIONS, encoding="utf-8")
    for number, markdown in enumerate(batch_markdown, start=1):
        (reviewer / f"batch_{number:02d}.md").write_text(markdown, encoding="utf-8")
    write_json(reviewer / "ballot.json", {"reviewer": None, "cases": ballot})
    write_json(coordinator / "manifest.json", manifest)
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=DATA)
    parser.add_argument("--annotations", type=Path, default=ANNOTATIONS)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=20261125)
    args = parser.parse_args(argv)
    try:
        manifest = build(args.data, args.annotations, args.output, args.seed)
    except (OSError, ValueError) as error:
        parser.exit(1, f"error: {error}\n")
    print(f"Built {len(manifest['cases'])} cases from {manifest['source_turn_count']} source turns.")
    for batch, count in manifest["priority_counts"].items():
        print(f"  {batch}: {count}")
    print(f"Reviewer packet: {args.output / 'reviewer'}")
    print(f"Coordinator manifest: {args.output / 'coordinator' / 'manifest.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
