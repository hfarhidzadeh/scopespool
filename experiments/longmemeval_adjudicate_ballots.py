"""Validate two LongMemEval ballots and prepare a manual adjudication worksheet."""

import argparse
import hashlib
import json
import re
from pathlib import Path


EVIDENCE_STATUSES = ("supported", "unsupported", "uncertain")
RELATION_STATUSES = ("labelled", "no_relation", "uncertain")
RELATIONS = ("supersedes", "adds_to", "independent")


def read_json(path):
    def unique_keys(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError(f"duplicate key {key!r}")
            result[key] = value
        return result

    raw = path.read_bytes()
    try:
        data = json.loads(raw, object_pairs_hook=unique_keys)
    except ValueError as error:
        raise ValueError(f"{path}: {error}") from error
    return data, hashlib.sha256(raw).hexdigest()


def nonblank(value):
    return isinstance(value, str) and bool(value.strip())


def manifest_cases(manifest):
    if not isinstance(manifest, dict) or type(manifest.get("format_version")) is not int:
        raise ValueError("manifest: missing format_version")
    if manifest["format_version"] != 1:
        raise ValueError("manifest: expected format_version 1")
    for field in ("data_sha256", "annotations_sha256"):
        value = manifest.get(field)
        if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
            raise ValueError(f"manifest: invalid {field}")
    cases = manifest.get("cases")
    if not isinstance(cases, dict) or not cases:
        raise ValueError("manifest: cases must be a nonempty object")
    question_ids = set()
    for case_id, case in cases.items():
        if not nonblank(case_id) or not isinstance(case, dict):
            raise ValueError("manifest: invalid case entry")
        question_id = case.get("question_id")
        if not nonblank(question_id) or question_id in question_ids:
            raise ValueError(f"manifest case {case_id}: missing or repeated question_id")
        if not nonblank(case.get("priority_batch")):
            raise ValueError(f"manifest case {case_id}: missing priority_batch")
        turns = case.get("shown_user_turn_ids")
        if (not isinstance(turns, list) or not turns or not all(map(nonblank, turns))
                or len(set(turns)) != len(turns)):
            raise ValueError(f"manifest case {case_id}: invalid shown_user_turn_ids")
        question_ids.add(question_id)
    return cases


def validate_turn(turn, allowed):
    if not isinstance(turn, str) or turn not in allowed:
        raise ValueError(f"reference {turn!r} is not a listed user turn")


def validate_groups(groups, allowed):
    if not isinstance(groups, list):
        raise ValueError("required_evidence_groups must be a list")
    normalized = set()
    for group in groups:
        if not isinstance(group, list) or not group:
            raise ValueError("each evidence group must be a nonempty list of turn IDs")
        for turn in group:
            validate_turn(turn, allowed)
        if len(set(group)) != len(group):
            raise ValueError("evidence group repeats a turn ID")
        key = tuple(sorted(group))
        if key in normalized:
            raise ValueError("required_evidence_groups repeats a group")
        normalized.add(key)
    return [list(group) for group in sorted(normalized)]


def validate_relations(relations, allowed):
    if not isinstance(relations, list):
        raise ValueError("relations must be a list")
    normalized = []
    pairs = set()
    for edge in relations:
        if not isinstance(edge, dict):
            raise ValueError("each relation must be an object")
        old, new = edge.get("old"), edge.get("new")
        validate_turn(old, allowed)
        validate_turn(new, allowed)
        if old == new:
            raise ValueError("relation endpoints must be different turns")
        pair = frozenset((old, new))
        if pair in pairs:
            raise ValueError("relations repeat a pair of turns")
        pairs.add(pair)
        relation, rationale = edge.get("relation"), edge.get("rationale")
        if relation not in RELATIONS:
            raise ValueError(f"relation must be one of {', '.join(RELATIONS)}")
        if not nonblank(rationale):
            raise ValueError("each relation needs a rationale")
        normalized.append(dict(old=old, new=new, relation=relation, rationale=rationale.strip()))
    return sorted(normalized, key=lambda edge: (edge["old"], edge["new"]))


def validate_judgment(value, allowed):
    if not isinstance(value, dict):
        raise ValueError("missing case judgment")
    evidence, relation = value.get("evidence_status"), value.get("relation_status")
    if evidence not in EVIDENCE_STATUSES:
        raise ValueError(f"evidence_status must be one of {', '.join(EVIDENCE_STATUSES)}")
    if relation not in RELATION_STATUSES:
        raise ValueError(f"relation_status must be one of {', '.join(RELATION_STATUSES)}")
    answer, notes = value.get("answer"), value.get("notes")
    for field, content in (("answer", answer), ("notes", notes)):
        if content is not None and not nonblank(content):
            raise ValueError(f"{field} must be nonempty text or null")
    groups = validate_groups(value.get("required_evidence_groups"), allowed)
    edges = validate_relations(value.get("relations"), allowed)
    if evidence == "supported":
        if not nonblank(answer) or not groups:
            raise ValueError("supported evidence requires an answer and at least one evidence group")
    elif groups:
        raise ValueError("required_evidence_groups must be empty for unsupported or uncertain evidence")
    if (relation == "labelled") != bool(edges):
        raise ValueError("relations must be nonempty for labelled status and empty otherwise")
    if (evidence != "supported" or relation == "uncertain") and not nonblank(notes):
        raise ValueError("unsupported or uncertain judgments require explanatory notes")
    return dict(answer=answer.strip() if answer else None, evidence_status=evidence,
                required_evidence_groups=groups, relation_status=relation, relations=edges,
                notes=notes.strip() if notes else None)


def validate_ballot(ballot, cases, selected, label):
    if not isinstance(ballot, dict) or not isinstance(ballot.get("cases"), dict):
        raise ValueError(f"{label}: ballot must contain a cases object")
    answers = ballot["cases"]
    unknown = sorted(answers.keys() - cases.keys())
    if unknown:
        raise ValueError(f"{label}: unknown case IDs: {', '.join(unknown)}")
    problems = []
    reviewer = ballot.get("reviewer")
    if not nonblank(reviewer):
        problems.append("reviewer must be a nonempty identifier")
    judgments = {}
    for case_id in selected:
        case = cases[case_id]
        try:
            judgments[case_id] = validate_judgment(
                answers.get(case_id), set(case["shown_user_turn_ids"])
            )
        except ValueError as error:
            problems.append(f"{case_id}: {error}")
    if problems:
        examples = "\n  ".join(problems[:8])
        if len(problems) > 8:
            examples += f"\n  ... and {len(problems) - 8} more"
        raise ValueError(f"{label}: incomplete or invalid ballot ({len(problems)} issues)\n  {examples}")
    return reviewer.strip(), judgments


def compare(left, right):
    def relation_keys(judgment):
        return {(edge["old"], edge["new"], edge["relation"]) for edge in judgment["relations"]}

    evidence = left["evidence_status"], right["evidence_status"]
    relation = left["relation_status"], right["relation_status"]
    answers = [item["answer"] for item in (left, right)]
    return {
        "evidence_status": evidence[0] == evidence[1],
        "answer_text": (" ".join(answers[0].split()) == " ".join(answers[1].split()))
        if all(answers) else None,
        "required_evidence_groups": left["required_evidence_groups"] == right["required_evidence_groups"]
        if evidence == ("supported", "supported") else None,
        "relation_status": relation[0] == relation[1],
        "relation_edges": relation_keys(left) == relation_keys(right)
        if "uncertain" not in relation else None,
    }


def make_worksheet(manifest_path, left_path, right_path, batch):
    manifest, manifest_hash = read_json(manifest_path)
    cases = manifest_cases(manifest)
    selected = [case_id for case_id in sorted(cases)
                if batch is None or cases[case_id]["priority_batch"] == batch]
    if not selected:
        raise ValueError(f"manifest: no cases for priority batch {batch!r}")
    ballots = []
    for index, path in enumerate((left_path, right_path), start=1):
        ballot, digest = read_json(path)
        reviewer, judgments = validate_ballot(ballot, cases, selected, f"ballot {index}")
        ballots.append((reviewer, digest, judgments))
    if ballots[0][0].casefold() == ballots[1][0].casefold():
        raise ValueError("ballots must have distinct reviewer identifiers")

    worksheet = {}
    agreement = {}
    for case_id in selected:
        left, right = (ballot[2][case_id] for ballot in ballots)
        matches = compare(left, right)
        flags = [f"{field}_differs" for field, match in matches.items() if match is False]
        if bool(left["answer"]) != bool(right["answer"]):
            flags.append("answer_present_in_one_ballot")
        if any("uncertain" in (item["evidence_status"], item["relation_status"])
               for item in (left, right)):
            flags.append("uncertain_judgment")
        for field, match in matches.items():
            key = "not_comparable" if match is None else "match" if match else "differ"
            counts = agreement.setdefault(field, dict(match=0, differ=0, not_comparable=0))
            counts[key] += 1
        worksheet[case_id] = {
            "question_id": cases[case_id]["question_id"],
            "priority_batch": cases[case_id]["priority_batch"],
            "comparisons": matches,
            "attention_flags": flags,
            "judgments": [left, right],
            "manual_adjudication": dict(disposition=None, answer=None, evidence_status=None,
                                        required_evidence_groups=[], relation_status=None,
                                        relations=[], notes=None),
        }
    return {
        "format_version": 1,
        "status": "manual_adjudication_required",
        "source": {
            "manifest_sha256": manifest_hash,
            "data_sha256": manifest["data_sha256"],
            "annotations_sha256": manifest["annotations_sha256"],
            "ballots": [dict(reviewer=reviewer, ballot_sha256=digest)
                        for reviewer, digest, _ in ballots],
            "priority_batch": batch,
        },
        "summary": {
            "cases_compared": len(worksheet),
            "cases_flagged": sum(bool(case["attention_flags"]) for case in worksheet.values()),
            "comparisons": agreement,
        },
        "cases": worksheet,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--ballot-a", required=True, type=Path)
    parser.add_argument("--ballot-b", required=True, type=Path)
    parser.add_argument("--batch", help="compare only this manifest priority batch")
    parser.add_argument("--output", required=True, type=Path, help="new local worksheet JSON")
    args = parser.parse_args(argv)
    try:
        result = make_worksheet(args.manifest, args.ballot_a, args.ballot_b, args.batch)
        with args.output.open("x", encoding="utf-8") as handle:
            json.dump(result, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
    except (OSError, ValueError) as error:
        parser.exit(1, f"error: {error}\n")
    summary = result["summary"]
    print(f"Compared {summary['cases_compared']} cases. Flagged {summary['cases_flagged']} "
          f"for attention. Manual worksheet saved to {args.output}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
