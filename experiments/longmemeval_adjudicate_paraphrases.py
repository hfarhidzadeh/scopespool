"""Validate two paraphrase ballots and prepare a manual adjudication worksheet."""

import argparse
import hashlib
import json
import re
from collections import Counter
from pathlib import Path


RELATIONS = ("equivalent", "incompatible", "distinct_compatible", "open")
SPLITS = ("development", "holdout")
JUDGMENT_FIELDS = {"relation", "usable", "rationale", "notes"}


def sha256(data):
    return hashlib.sha256(data).hexdigest()


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
        return json.loads(raw, object_pairs_hook=unique_keys), sha256(raw)
    except ValueError as error:
        raise ValueError(f"{path}: {error}") from error


def nonblank(value):
    return isinstance(value, str) and bool(value.strip())


def validate_manifest(manifest, packet_digest):
    if (not isinstance(manifest, dict) or type(manifest.get("format_version")) is not int
            or manifest["format_version"] != 1):
        raise ValueError("manifest: expected format_version 1")
    for field in ("data_sha256", "reviewer_zip_sha256"):
        value = manifest.get(field)
        if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
            raise ValueError(f"manifest: invalid {field}")
    if manifest["reviewer_zip_sha256"] != packet_digest:
        raise ValueError("reviewer ZIP hash does not match the manifest")

    cases = manifest.get("cases")
    if not isinstance(cases, dict) or not cases:
        raise ValueError("manifest: cases must be a nonempty object")
    for case_id, case in cases.items():
        if not nonblank(case_id) or not isinstance(case, dict):
            raise ValueError("manifest: invalid case entry")
        for field in ("source_family", "source_question", "source_session"):
            if not nonblank(case.get(field)):
                raise ValueError(f"manifest case {case_id}: missing {field}")
    family_counts = manifest.get("source_family_counts")
    if (not isinstance(family_counts, dict)
            or any(type(count) is not int for count in family_counts.values())
            or family_counts != Counter(case["source_family"] for case in cases.values())):
        raise ValueError("manifest: source_family_counts do not match cases")
    return cases


def validate_judgment(judgment):
    if not isinstance(judgment, dict) or set(judgment) != JUDGMENT_FIELDS:
        raise ValueError("expected relation, usable, rationale, and notes")
    usable = judgment["usable"]
    if type(usable) is not bool:
        raise ValueError("usable must be true or false")
    relation = judgment["relation"]
    if usable and relation not in RELATIONS:
        raise ValueError(f"usable cases require a relation from {', '.join(RELATIONS)}")
    if not usable and relation is not None:
        raise ValueError("unusable cases require a null relation")
    rationale, notes = judgment["rationale"], judgment["notes"]
    if not nonblank(rationale):
        raise ValueError("rationale must be nonempty text")
    if notes is not None and not nonblank(notes):
        raise ValueError("notes must be nonempty text or null")
    return dict(relation=relation, usable=usable, rationale=rationale.strip(),
                notes=notes.strip() if notes else None)


def validate_ballot(ballot, cases, label):
    if not isinstance(ballot, dict) or not isinstance(ballot.get("cases"), dict):
        raise ValueError(f"{label}: ballot must contain a cases object")
    answers = ballot["cases"]
    problems = []
    for label_text, ids in (("unknown", answers.keys() - cases.keys()),
                            ("missing", cases.keys() - answers.keys())):
        if ids:
            problems.append(f"{label_text} case IDs: {', '.join(sorted(ids))}")
    reviewer = ballot.get("reviewer")
    if not nonblank(reviewer):
        problems.append("reviewer must be a nonempty identifier")
    judgments = {}
    for case_id in sorted(cases.keys() & answers.keys()):
        try:
            judgments[case_id] = validate_judgment(answers[case_id])
        except ValueError as error:
            problems.append(f"{case_id}: {error}")
    if problems:
        examples = "\n  ".join(problems[:8])
        if len(problems) > 8:
            examples += f"\n  ... and {len(problems) - 8} more"
        raise ValueError(f"{label}: incomplete or invalid ballot ({len(problems)} issues)\n  {examples}")
    return reviewer.strip(), judgments


def validate_split(split, cases):
    families = {case["source_family"] for case in cases.values()}
    if not isinstance(split, dict) or set(split) != families:
        raise ValueError("family split must assign exactly the manifest's source families")
    if any(value not in SPLITS for value in split.values()) or set(split.values()) != set(SPLITS):
        raise ValueError("family split must assign each family to development or holdout, with both present")
    for field in ("source_question", "source_session"):
        assigned = {}
        for case in cases.values():
            source, target = case[field], split[case["source_family"]]
            if assigned.setdefault(source, target) != target:
                raise ValueError(f"family split places {field} {source!r} in both splits")
    return dict(sorted(split.items()))


def worksheet_case(case, left, right):
    usability = "match" if left["usable"] == right["usable"] else "differ"
    if not (left["usable"] and right["usable"]):
        relation = "not_comparable"
    else:
        relation = "match" if left["relation"] == right["relation"] else "differ"
    comparisons = dict(usability=usability, relation=relation)
    flags = [f"{field}_differs" for field, result in comparisons.items() if result == "differ"]
    if not (left["usable"] and right["usable"]):
        flags.append("unusable_judgment")
    if any(judgment["relation"] == "open" for judgment in (left, right)):
        flags.append("open_judgment")
    return {
        "source_family": case["source_family"],
        "comparisons": comparisons,
        "attention_flags": flags,
        "judgments": [left, right],
        "manual_adjudication": dict(usable=None, relation=None, rationale=None, notes=None),
    }


def summarize(entries):
    comparisons = {}
    for field in ("usability", "relation"):
        counts = Counter(entry["comparisons"][field] for entry in entries)
        comparisons[field] = {key: counts[key] for key in ("match", "differ", "not_comparable")}
    votes = []
    for index in range(2):
        judgments = [entry["judgments"][index] for entry in entries]
        counts = Counter(judgment["relation"] if judgment["usable"] else "unusable"
                         for judgment in judgments)
        votes.append({key: counts[key] for key in (*RELATIONS, "unusable")})
    return {
        "cases_compared": len(entries),
        "cases_flagged": sum(bool(entry["attention_flags"]) for entry in entries),
        "comparisons": comparisons,
        "reviewer_judgments": votes,
    }


def make_worksheet(manifest_path, packet_path, left_path, right_path, split_path=None):
    manifest, manifest_hash = read_json(manifest_path)
    packet_hash = sha256(packet_path.read_bytes())
    cases = validate_manifest(manifest, packet_hash)
    ballots = []
    for index, path in enumerate((left_path, right_path), start=1):
        ballot, digest = read_json(path)
        reviewer, judgments = validate_ballot(ballot, cases, f"ballot {index}")
        ballots.append((reviewer, digest, judgments))
    if ballots[0][0].casefold() == ballots[1][0].casefold():
        raise ValueError("ballots must have distinct reviewer identifiers")

    family_split = dict.fromkeys(sorted(manifest["source_family_counts"]))
    split_hash = None
    if split_path is not None:
        proposed_split, split_hash = read_json(split_path)
        family_split = validate_split(proposed_split, cases)

    entries = {}
    by_family = {family: [] for family in family_split}
    for case_id in sorted(cases):
        left, right = (ballot[2][case_id] for ballot in ballots)
        entry = worksheet_case(cases[case_id], left, right)
        entries[case_id] = entry
        by_family[entry["source_family"]].append(entry)
    return {
        "format_version": 1,
        "status": "manual_adjudication_required",
        "source": {
            "manifest_sha256": manifest_hash,
            "data_sha256": manifest["data_sha256"],
            "reviewer_zip_sha256": packet_hash,
            "family_split_sha256": split_hash,
            "ballots": [dict(reviewer=reviewer, ballot_sha256=digest)
                        for reviewer, digest, _ in ballots],
        },
        "summary": summarize(list(entries.values())),
        "by_source_family": {family: summarize(rows) for family, rows in by_family.items()},
        "family_split": family_split,
        "cases": entries,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--packet", required=True, type=Path, help="original reviewer ZIP")
    parser.add_argument("--ballot-a", required=True, type=Path)
    parser.add_argument("--ballot-b", required=True, type=Path)
    parser.add_argument("--family-split", type=Path, help="family names mapped to development or holdout")
    parser.add_argument("--output", required=True, type=Path, help="new local worksheet JSON")
    args = parser.parse_args(argv)
    try:
        result = make_worksheet(args.manifest, args.packet, args.ballot_a, args.ballot_b,
                                args.family_split)
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
