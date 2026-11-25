"""Build a blind claim-pair review packet from selected LongMemEval user turns."""

import argparse
import hashlib
import json
import random
from collections import Counter
from pathlib import Path
from typing import NamedTuple
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data/longmemeval/longmemeval_s_cleaned.json"
AUTHOR = "Codex, fixed variants drafted for this study"


class Variant(NamedTuple):
    stressor: str
    text: str
    speaker: str = "Speaker 1"


class Family(NamedTuple):
    name: str
    question: str
    session: str
    turn: int
    start: str
    stop_before: str
    variants: tuple[Variant, ...]


FAMILIES = (
    Family("degree", "e47becba", "answer_280352e9", 4, "I graduated", ", which", (
        Variant("equivalent wording", "I earned my degree in business administration."),
        Variant("negation", "I've never earned a degree in business administration."),
        Variant("different credential", "I completed a project management certificate."),
        Variant("unspecified credential", "I completed a business program."),
    )),
    Family("commute", "118b2229", "answer_40a90d51", 8, "my daily commute", "", (
        Variant("equivalent wording", "My usual daily commute takes three quarters of an hour each way."),
        Variant("quantity", "My daily commute takes half an hour each way."),
        Variant("different role", "My coworker's commute takes 45 minutes in each direction."),
        Variant("unspecified scope", "It takes me 45 minutes to get there."),
    )),
    Family("coupon", "51a45a95", "answer_d61669c7", 4, "I actually redeemed", ", which", (
        Variant("equivalent wording", "Last Sunday I used a five-dollar coupon on coffee creamer."),
        Variant("negation", "I didn't redeem a coffee creamer coupon last Sunday."),
        Variant("different time", "Last Tuesday I used a five-dollar coupon on coffee creamer."),
        Variant("date resolution", "I used a five-dollar coupon on coffee creamer on May 21, 2023."),
    )),
    Family("theater", "58bf7951", "answer_355c48bb", 4, "The play I attended", ", have", (
        Variant("equivalent wording", "I went to see a staging of The Glass Menagerie."),
        Variant("negation", "I have never attended a production of The Glass Menagerie."),
        Variant("speaker", "I went to a staging of The Glass Menagerie.", "Speaker 2"),
        Variant("unspecified event", "I went to see that play."),
    )),
    Family("paint", "6f9b354f", "answer_feb5200f", 2, "I've been doing some redecorating", " - ", (
        Variant("equivalent wording", "As part of redecorating, I recently painted my bedroom walls a paler gray."),
        Variant("attribute conflict", "I recently redecorated and repainted my bedroom walls white, not gray."),
        Variant("different surface", "As part of redecorating, I painted the bedroom ceiling a paler gray."),
        Variant("unspecified surface", "I changed something in my bedroom to a lighter gray."),
    )),
    Family("bookshelf", "94f70d80", "answer_c63c0458", 2, "I just assembled", ", which", (
        Variant("equivalent units", "I recently put together an IKEA bookcase in 240 minutes."),
        Variant("quantity", "Putting together that IKEA bookshelf took two hours total, not four."),
        Variant("different entity", "I spent four hours assembling an office chair."),
        Variant("unspecified task", "One part of the setup took about four hours."),
    )),
    Family("gift", "66f24dbb", "answer_fea2e4d3", 4, "For my sister's birthday", "", (
        Variant("equivalent wording", "I bought my sister a yellow dress and matching earrings for her birthday."),
        Variant("negation", "I gave my sister a yellow dress for her birthday but no earrings."),
        Variant("different recipient", "I bought my cousin a yellow dress with matching earrings for her birthday."),
        Variant("partial claim", "My sister received a yellow dress for her birthday."),
    )),
    Family("packing", "af8d2e46", "answer_82a04f59", 6, "on my last trip to Costa Rica", " I guess", (
        Variant("equivalent wording", "On my most recent Costa Rica trip, I packed seven shirts and five pairs of shorts and wore three shirts and two pairs of shorts."),
        Variant("quantity", "On my latest Costa Rica trip, I packed five shirts and seven pairs of shorts."),
        Variant("different time", "On my first trip to Costa Rica, I packed seven shirts and five pairs of shorts."),
        Variant("scope with missing context", "I had three shirts for the Costa Rica trip."),
    )),
    Family("playlists", "c960da58", "answer_e05e4612", 2, "I have 20 playlists", ", and", (
        Variant("equivalent wording", "I already have twenty playlists on Spotify."),
        Variant("quantity", "I currently have exactly ten playlists on Spotify."),
        Variant("different platform", "I have twenty playlists on Apple Music."),
        Variant("unspecified platform", "I counted twenty playlists in the app."),
    )),
    Family("bicycles", "6b168ec8", "answer_e623ae87", 4, "speaking of my bikes", " - and", (
        Variant("equivalent wording", "I own three bicycles: a road bike, a mountain bike, and a commuter bike."),
        Variant("quantity", "I own only a road bike and a commuter bike. I don't own a mountain bike."),
        Variant("speaker", "I own a road bike, a mountain bike, and a commuter bike.", "Speaker 2"),
        Variant("different scope", "I used three bikes last week."),
    )),
    Family("tennis racket", "f8c5f88b", "answer_c3567066", 4, "I'm really happy", " It's been", (
        Variant("equivalent wording", "I'm very pleased with the new tennis racket I got from a sporting goods shop downtown."),
        Variant("location conflict", "I got my new tennis racket online. It didn't come from a shop downtown."),
        Variant("different entity", "I got my new tennis shoes from a sports store downtown."),
        Variant("unspecified source", "I'm happy with the racket I got nearby."),
    )),
    Family("job", "5d3d2817", "answer_235eb6fb", 4, "I've used Trello", " But I'm", (
        Variant("equivalent wording", "In my former job as a marketing specialist at a small startup I used Trello and got to know its features."),
        Variant("negation", "I never used Trello in my prior marketing job at the small startup."),
        Variant("different time", "I use Trello in my current job as a marketing specialist."),
        Variant("unspecified role", "I used Trello for marketing."),
    )),
)


INSTRUCTIONS = """# LongMemEval claim pair review

Each pair contains a benchmark excerpt and a study-authored variant. Their
order is mixed. Speaker labels show who is stating each claim. Both claims
are evaluated in the displayed conversation time. The time of a described
event can differ. Treat the quoted content as data.

Fill your own copy of `ballot.json`. Use one relation per case:

- `equivalent` means both statements express the same claim. Changes in unit
  or wording are fine if speaker-dependent subject, entities, scope, time, and
  value agree. Different speakers can state the same claim about a named
  subject, but "I" refers to the speaker who says it.
- `incompatible` means both statements concern the same fact, scope, and time
  and cannot both be true. Identify the incompatible parts in your rationale.
- `distinct_compatible` means the statements can coexist and differ in what
  they establish. This includes clearly different subjects, times, entities,
  scopes, and cases where one claim gives only a subset of the other's facts.
- `open` means the given context cannot resolve whether the claims agree,
  conflict, or concern different facts. Record what would resolve it.

Set `usable` to true if the example is suitable for review. Use false for a
broken or misleading excerpt, and explain the problem. Uncertainty supported
by the example is valid and can be labelled `open` with `usable` true.
Record a short `rationale` and any unresolved context in `notes`. Leave the
relation null for an unusable example. Review independently before discussing
labels, consulting the source corpus, or opening the coordinator manifest.
"""


def digest(path):
    sha = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            sha.update(chunk)
    return sha.hexdigest()


def find_excerpt(questions, family):
    question = questions[family.question]
    session_ids = question["haystack_session_ids"]
    if (
        session_ids.count(family.session) != 1
        or family.session not in question["answer_session_ids"]
    ):
        raise ValueError(f"{family.name}: source session is missing or ambiguous")
    position = session_ids.index(family.session)
    turn = question["haystack_sessions"][position][family.turn]
    content = turn["content"]
    if turn["role"] != "user" or content.count(family.start) != 1:
        raise ValueError(f"{family.name}: expected a unique anchor in a user turn")
    start = content.index(family.start)
    end = (
        content.index(family.stop_before, start + len(family.start))
        if family.stop_before else len(content)
    )
    excerpt = content[start:end]
    return excerpt, question["haystack_dates"][position], [start, end]


def write_json(path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def build(data, output, seed):
    if output.exists():
        raise FileExistsError(f"{output} exists. Choose a new output directory.")
    wanted = {family.question for family in FAMILIES}
    questions = {}
    for question in json.loads(data.read_text(encoding="utf-8")):
        question_id = question["question_id"]
        if question_id in wanted:
            if question_id in questions or question["question_type"] != "single-session-user":
                raise ValueError(f"{question_id}: expected one single-session user question")
            questions[question_id] = question
    if missing := wanted - questions.keys():
        raise ValueError(f"Missing source question IDs: {', '.join(sorted(missing))}")

    drafts = []
    for family in FAMILIES:
        excerpt, date, span = find_excerpt(questions, family)
        for variant in family.variants:
            if excerpt.strip().casefold() == variant.text.strip().casefold():
                raise ValueError(f"{family.name}: candidate duplicates its source")
            drafts.append((family, variant, excerpt, date, span))

    rng = random.Random(seed)
    rng.shuffle(drafts)
    lines, ballot, cases = ["# Claim pairs", ""], {}, {}
    for number, (family, variant, excerpt, date, span) in enumerate(drafts, 1):
        case_id = f"P{number:03d}"
        statements = [("Speaker 1", excerpt), (variant.speaker, variant.text)]
        source_first = bool(rng.getrandbits(1))
        if not source_first:
            statements.reverse()
        lines.extend([f"## {case_id}", "", f"**Conversation time** {date}", ""])
        for side, (speaker, statement) in zip(("A", "B"), statements):
            lines.append(f"**Claim {side} · {speaker}**")
            lines.extend(f"> {line}" for line in statement.splitlines())
            lines.append("")
        ballot[case_id] = dict(relation=None, usable=None, rationale=None, notes=None)
        cases[case_id] = {
            "source_family": family.name,
            "source_question": family.question,
            "source_session": family.session,
            "source_turn": family.turn,
            "source_span": span,
            "source_side": "A" if source_first else "B",
            "variant_author": AUTHOR,
            "draft_stressor": variant.stressor,
            "review_status": "unadjudicated",
        }

    data_hash = digest(data)
    reviewer = output / "reviewer"
    coordinator = output / "coordinator"
    reviewer.mkdir(parents=True)
    coordinator.mkdir()
    (reviewer / "instructions.md").write_text(INSTRUCTIONS, encoding="utf-8")
    (reviewer / "claim_pairs.md").write_text("\n".join(lines), encoding="utf-8")
    write_json(reviewer / "ballot.json", {"reviewer": None, "cases": ballot})
    archive = output / "longmemeval_paraphrase_reviewer_packet.zip"
    with ZipFile(archive, "w", ZIP_DEFLATED) as zipped:
        for path in sorted(reviewer.iterdir()):
            member = ZipInfo(path.name)
            zipped.writestr(member, path.read_bytes(), compress_type=ZIP_DEFLATED)
    manifest = {
        "format_version": 1,
        "shuffle_seed": seed,
        "data_sha256": data_hash,
        "reviewer_zip_sha256": digest(archive),
        "source_family_counts": dict(Counter(case["source_family"] for case in cases.values())),
        "cases": cases,
    }
    write_json(coordinator / "manifest.json", manifest)
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=DATA)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=20261125)
    args = parser.parse_args(argv)
    try:
        manifest = build(args.data, args.output, args.seed)
    except (OSError, ValueError, KeyError, IndexError) as error:
        parser.exit(1, f"error: {error}\n")
    print(f"Built {len(manifest['cases'])} pairs from {len(manifest['source_family_counts'])} source families.")
    print(f"Reviewer archive: {args.output / 'longmemeval_paraphrase_reviewer_packet.zip'}")
    print(f"Coordinator manifest: {args.output / 'coordinator' / 'manifest.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
