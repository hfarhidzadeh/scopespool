"""Cross-user disputes on real conversation text: detected, and blind to hidden claims?

Question (follows H8 of section 9 of docs/multi_user_memory_review.md, which was
tested on invented "k0 is v1" claims). When two members of a channel state the
older and the newer side of a real knowledge update as claims on one key, does
``disputes(viewers)`` show the disagreement with the real sentences, and does
``who_knows`` attribute them by statement and acknowledgement only? And, as in
H8, does a claim the viewers cannot see leave both answers unchanged, now that
the claim texts are long, real, and sometimes repeat a visible claim word for
word?

Data. LongMemEval_S (cleaned) with the reviewed v3 annotations
(``eval/longmemeval_knowledge_update_annotations_v3_reviewed.json``), no LLM.
A pair is one ``supersedes`` edge of a question whose category is ``current``:
its older turn and its newer turn, as user text (the parser of
``dynmemory.longmemeval``). Pairs whose two texts are the same after stripping
and case-folding (the store's default claim equivalence) are dropped and
counted. Each pair is run with seeds r = 0 to R-1 (default R = 10); a trial is
(pair, r).

The staging is invented; the words are not. Members alice, bob, carol and dana;
dana is a workspace admin. ``history`` holds all four; ``dm`` holds bob and dana,
so alice and carol cannot see anything drawn from a ``dm`` message. One key,
``update``.

- Visible script ("<pair>-<r>-visible"). The older speaker X is alice or carol
  and the newer speaker Y the other one. Steps in order: 2 to 6 background
  messages (other user turns of the same question, sampled and kept in their
  original order, each said by alice or carol); X says the older turn as a
  message and claims it on ``update`` from that message; 1 to 4 more background
  messages; Y says the newer turn and claims it the same way; with probability
  0.5, X replies to Y's message (X acknowledges the update).
- Hidden script ("<pair>-<r>-hidden"). 1 to 3 claims on ``update`` by bob or
  dana, each from its own ``dm`` message, each inserted at a random position
  after the older claim. Each claim's text is the older turn, the newer turn, or
  another user turn of the question, with equal probability; dana's claims
  carry admin authority. With probability 0.5 each is followed by its writer
  reacting to its own ``dm`` message.

Worlds. W: the visible script alone. H: with the hidden script. H2: H built
again. V (positive control): as H, but the hidden claims come from ``history``
messages, so alice and carol can see them.

Observations, for audiences [alice], [carol] and [alice, carol]: the dispute
tables (key, open, and per row speaker, text, status, standing, name) and the
who_knows of the older and the newer claim (stated, acknowledged, had access).
Claims are named "older" and "newer" by their role in the visible script;
any other claim shows as "?".

Checks, per trial.
- Determinism (negative control): H2 equals H.
- Detection (positive control): in W, for every audience, there is exactly one
  dispute; its key is ``update``, it is open, and its rows are X saying the
  older text and Y saying the newer text, both standing and ``disputed``.
- Power (positive control): V differs from W.
- Acknowledgement counts (positive control): in W and H, for audience [alice],
  the newer claim's who_knows lists Y as stating it, and X as acknowledging it
  exactly when X replied.
- Presence does not count (negative control): in W and H, for audience [alice],
  bob and dana appear in both claims' "had access" and in neither "stated" nor
  "acknowledged".
- Noninterference: H equals W in every observation.

Decision rule, fixed before running:
  1. Determinism holds in every trial.
  2. Detection holds in every trial.
  3. Power: V differs from W in at least 50% of trials.
  4. Acknowledgement counts in every trial.
  5. Presence does not count in every trial.
  6. Noninterference holds in every trial.
Verdict: "inconclusive (control <n> failed)" if any of rules 1 to 5 fails;
otherwise "disputes and who-knows pass on real text" if rule 6 holds, else
"they fail rule 6 (first failing trial <pair>/<r>)".

Reported, not part of the verdict: pairs and questions used, pairs dropped as
identical; in V, the share of trials whose dispute is closed (an admin claim by
dana settled it) and the statuses then shown; hidden claims that restate a
visible text word for word.

Validation (positive control against the store), fixed before running: with
``--fault administrative`` the script replaces ``disputes`` and ``who_knows``
with versions that compute over every memory (still returning None for a memory
hidden from the viewers), as in H8. Rule 6 must then fail in at least 25% of
trials, or this experiment cannot detect the leak it is for.

Limits. Who said which turn is staged. A claim's value is a whole user turn and
the store compares values by exact text (after case-folding), so this tests
how disputes are reported and hidden, not whether the store can tell that two
differently worded turns say the same thing; that needs a ``claim_equivalence``
and is not tested here.

Run from the project root:

    python3 -I experiments/longmemeval_cross_user_disputes.py
    python3 -I experiments/longmemeval_cross_user_disputes.py --fault administrative \\
        --output experiments/results/longmemeval_cross_user_disputes_fault
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from dynmemory import MemoryStore, MemoryType  # noqa: E402
from dynmemory.longmemeval import question_memories  # noqa: E402
from dynmemory.store import SCHEMA_VERSION  # noqa: E402

DATA = ROOT / "data" / "longmemeval" / "longmemeval_s_cleaned.json"
ANNOTATIONS = ROOT / "eval" / "longmemeval_knowledge_update_annotations_v3_reviewed.json"
MEMBERS = ("alice", "bob", "carol", "dana")
VISIBLE_WRITERS = ("alice", "carol")
HIDDEN_WRITERS = ("bob", "dana")
AUDIENCES = (("alice",), ("carol",), ("alice", "carol"))
KEY = "update"
BACKGROUND_BEFORE = (2, 6)
BACKGROUND_BETWEEN = (1, 4)
REPLY_SHARE = 0.5
HIDDEN_CLAIMS = (1, 3)
HIDDEN_ACK = 0.5
POWER_SHARE = 0.5
FAULT_SHARE = 0.25
DEFAULT_REPS = 10
WORLDS = ("W", "H", "H2", "V")
CHECKS = ("determinism", "detection", "power", "acknowledgement", "presence", "noninterference")
RULES = {number: name for number, name in enumerate(CHECKS, start=1)}
CONTROL_RULES = (1, 2, 3, 4, 5)


def same_text(left: str, right: str) -> bool:
    return left.strip().casefold() == right.strip().casefold()


def make_pairs(questions: list, annotations: dict) -> tuple[list, dict]:
    """Every ``supersedes`` edge of a current question, as real text."""
    pairs, counts = [], {"edges": 0, "dropped_identical": 0}
    for question in questions:
        annotation = annotations.get(question["question_id"])
        if not annotation or annotation["category"] != "current":
            continue
        memories = question_memories(question)[0]
        for edge in annotation["supersession"]:
            if edge["relation"] != "supersedes":
                continue
            counts["edges"] += 1
            older, newer = memories[edge["old"]]["content"], memories[edge["new"]]["content"]
            if same_text(older, newer):
                counts["dropped_identical"] += 1
                continue
            pool = [memory["content"] for key, memory in memories.items()
                    if key not in (edge["old"], edge["new"])
                    and not same_text(memory["content"], older)
                    and not same_text(memory["content"], newer)]
            pairs.append({"question_id": question["question_id"], "old_id": edge["old"],
                          "new_id": edge["new"], "older": older, "newer": newer,
                          "pool": pool})
    counts["pairs"] = len(pairs)
    counts["questions"] = len({pair["question_id"] for pair in pairs})
    return pairs, counts


def _background(rng: random.Random, pool: list, count: int) -> list:
    picked = sorted(rng.sample(range(len(pool)), min(count, len(pool))))
    return [{"op": "say", "writer": rng.choice(VISIBLE_WRITERS), "text": pool[i]} for i in picked]


def make_trial(pair: dict, index: int, rep: int) -> dict:
    rng = random.Random("{}-{}-visible".format(index, rep))
    older_speaker = rng.choice(VISIBLE_WRITERS)
    newer_speaker = "carol" if older_speaker == "alice" else "alice"
    before = rng.randint(*BACKGROUND_BEFORE)
    between = rng.randint(*BACKGROUND_BETWEEN)
    background = _background(rng, pair["pool"], before + between)
    replied = rng.random() < REPLY_SHARE
    visible = background[:before]
    visible.append({"op": "claim", "writer": older_speaker, "text": pair["older"], "name": "older"})
    visible += background[before:]
    visible.append({"op": "claim", "writer": newer_speaker, "text": pair["newer"], "name": "newer"})
    if replied:
        visible.append({"op": "reply", "member": older_speaker})
    older_at = next(i for i, step in enumerate(visible) if step.get("name") == "older")
    hidden_rng = random.Random("{}-{}-hidden".format(index, rep))
    hidden = []
    for _ in range(hidden_rng.randint(*HIDDEN_CLAIMS)):
        source = hidden_rng.choice(("older", "newer", "other"))
        if source == "other" and pair["pool"]:
            text = hidden_rng.choice(pair["pool"])
        else:
            source = "newer" if source == "other" else source
            text = pair[source]
        writer = hidden_rng.choice(HIDDEN_WRITERS)
        hidden.append({
            "op": "claim", "writer": writer, "text": text, "source": source,
            "ack": hidden_rng.random() < HIDDEN_ACK,
            "position": hidden_rng.randint(older_at + 1, len(visible)),
        })
    return {"pair": index, "rep": rep, "question_id": pair["question_id"],
            "older_speaker": older_speaker, "newer_speaker": newer_speaker,
            "replied": replied, "older": pair["older"], "newer": pair["newer"],
            "visible": visible, "hidden": hidden}


def sequence(trial: dict, world: str) -> list:
    steps = [("visible", step) for step in trial["visible"]]
    if world == "W":
        return steps
    for claim in sorted(trial["hidden"], key=lambda item: -item["position"]):
        steps.insert(min(claim["position"], len(steps)), ("hidden", claim))
    return steps


def install_fault(name: str) -> None:
    """Make the store compute disputes and who-knows over every memory."""
    if name != "administrative":
        raise ValueError("unknown fault: {}".format(name))
    disputes, who_knows = MemoryStore.disputes, MemoryStore.who_knows

    def every_claim_disputes(store, *, viewers=None, channel=None, memory_key=None):
        return disputes(store, viewers=None, channel=channel, memory_key=memory_key)

    def every_claim_who_knows(store, memory_id, *, viewers=None):
        if store.get_memory(memory_id, viewers=viewers) is None:
            return None
        return who_knows(store, memory_id, viewers=None)

    MemoryStore.disputes = every_claim_disputes
    MemoryStore.who_knows = every_claim_who_knows


def observe(trial: dict, world: str) -> dict:
    hidden_source = "history" if world == "V" else "dm"
    with MemoryStore(":memory:") as store:
        for member in MEMBERS:
            store.join_channel("history", member)
        for member in HIDDEN_WRITERS:
            store.join_channel("dm", member)
        store.add_admin("dana")
        names, newer_message = {}, None
        for script, step in sequence(trial, world):
            if step["op"] == "say":
                store.for_writer(step["writer"]).add_message(step["text"], channel="history")
            elif step["op"] == "reply":
                store.for_writer(step["member"]).acknowledge(newer_message, "replied")
            else:
                writer = store.for_writer(step["writer"])
                source = "history" if script == "visible" else hidden_source
                message = writer.add_message(step["text"], channel=source)
                memory = writer.add_memory(
                    step["text"], MemoryType.FACT, channel="history",
                    memory_key=KEY, source_message_ids=[message.id],
                )
                if script == "visible":
                    names[memory.id] = step["name"]
                    if step["name"] == "newer":
                        newer_message = message.id
                elif step["ack"]:
                    writer.acknowledge(message.id, "reacted")
        reads = {}
        for audience in AUDIENCES:
            reads["+".join(audience)] = {
                "disputes": [
                    [dispute.memory_key, dispute.open,
                     [[row.speaker, row.says, row.status, row.standing,
                       names.get(row.memory_id, "?")] for row in dispute.rows]]
                    for dispute in store.disputes(viewers=list(audience))
                ],
                "who_knows": {
                    name: _knowledge(store.who_knows(memory_id, viewers=list(audience)))
                    for memory_id, name in sorted(names.items(), key=lambda item: item[1])
                },
            }
        return reads


def _knowledge(knowledge):
    if knowledge is None:
        return None
    return [list(knowledge.stated), list(knowledge.acknowledged), list(knowledge.had_access)]


def evaluate(trial: dict, seen: dict) -> dict:
    w, h, h2, v = (seen[world] for world in WORLDS)
    x, y = trial["older_speaker"], trial["newer_speaker"]
    expected = [KEY, True, [[x, trial["older"], "disputed", True, "older"],
                            [y, trial["newer"], "disputed", True, "newer"]]]
    detection = all(w[audience]["disputes"] == [expected] for audience in w)
    acknowledgement = all(
        world["alice"]["who_knows"]["newer"] is not None
        and world["alice"]["who_knows"]["newer"][0] == [y]
        and world["alice"]["who_knows"]["newer"][1] == ([x] if trial["replied"] else [])
        for world in (w, h)
    )
    presence = all(
        knowledge is not None and member in knowledge[2]
        and member not in knowledge[0] and member not in knowledge[1]
        for world in (w, h)
        for knowledge in world["alice"]["who_knows"].values()
        for member in HIDDEN_WRITERS
    )
    differs = ["{} ({})".format(audience, part) for audience in h for part in h[audience]
               if h[audience][part] != w[audience][part]]
    v_disputes = v["alice"]["disputes"]
    return {
        "pair": trial["pair"],
        "rep": trial["rep"],
        "question_id": trial["question_id"],
        "checks": {
            "determinism": h == h2,
            "detection": detection,
            "power": v != w,
            "acknowledgement": acknowledgement,
            "presence": presence,
            "noninterference": not differs,
        },
        "differs": differs[:3],
        "v_closed": bool(v_disputes) and not any(d[1] for d in v_disputes),
        "v_statuses": sorted({row[2] for d in v_disputes for row in d[2]}),
        "dana_claims": sum(c["writer"] == "dana" for c in trial["hidden"]),
        "hidden_restating": sum(c["source"] in ("older", "newer") for c in trial["hidden"]),
        "hidden_claims": len(trial["hidden"]),
    }


def run_trial(pair: dict, index: int, rep: int) -> dict:
    trial = make_trial(pair, index, rep)
    return evaluate(trial, {world: observe(trial, world) for world in WORLDS})


def summarise(trials: list) -> dict:
    with_dana = [t for t in trials if t["dana_claims"]]
    return {
        "checks": {
            name: {
                "held": sum(trial["checks"][name] for trial in trials),
                "not_held": ["{}/{}".format(t["pair"], t["rep"])
                             for t in trials if not t["checks"][name]],
            }
            for name in CHECKS
        },
        "v_closed": sum(t["v_closed"] for t in trials),
        "v_closed_with_dana": sum(t["v_closed"] for t in with_dana),
        "trials_with_dana": len(with_dana),
        "v_closed_statuses": sorted({s for t in trials if t["v_closed"] for s in t["v_statuses"]}),
        "hidden_claims": sum(t["hidden_claims"] for t in trials),
        "hidden_restating": sum(t["hidden_restating"] for t in trials),
        "failures": [{"trial": "{}/{}".format(t["pair"], t["rep"]), "differs": t["differs"]}
                     for t in trials if not t["checks"]["noninterference"]][:10],
    }


def decide(summary: dict, trials: int) -> dict:
    checks = summary["checks"]
    holds = {
        1: checks["determinism"]["held"] == trials,
        2: checks["detection"]["held"] == trials,
        3: checks["power"]["held"] >= POWER_SHARE * trials,
        4: checks["acknowledgement"]["held"] == trials,
        5: checks["presence"]["held"] == trials,
        6: checks["noninterference"]["held"] == trials,
    }
    failed = [number for number in CONTROL_RULES if not holds[number]]
    if failed:
        verdict = "inconclusive (control {} failed)".format(", ".join(map(str, failed)))
    elif holds[6]:
        verdict = "disputes and who-knows pass on real text"
    else:
        verdict = "they fail rule 6 (first failing trial {})".format(
            checks["noninterference"]["not_held"][0])
    decision = {"rule_{}_{}".format(number, name): holds[number] for number, name in RULES.items()}
    decision["verdict"] = verdict
    return decision


def validate_fault(summary: dict, trials: int) -> dict:
    failed = trials - summary["checks"]["noninterference"]["held"]
    return {"rule": 6, "failed": failed, "trials": trials,
            "detected": failed >= FAULT_SHARE * trials}


def _share(count: int, total: int) -> str:
    return "{} of {} ({:.1f}%)".format(count, total, 100.0 * count / total) if total else "-"


def render(report: dict) -> str:
    trials, summary, decision, counts = (report["trials"], report["summary"],
                                         report["decision"], report["pairs"])
    checks = summary["checks"]
    lines = [
        "# Cross-user disputes on real text",
        "",
        "LongMemEval_S user turns, reviewed v3 annotations; staged speakers; no LLM.",
        "{} trials: {} pairs from {} current questions ({} supersedes edges, {} dropped as "
        "identical text), {} seeds each.".format(
            trials, counts["pairs"], counts["questions"], counts["edges"],
            counts["dropped_identical"], report["reps"]),
        "Store under test: schema version {}{}.".format(
            report["store_schema_version"],
            "; injected fault: {}".format(report["fault"]) if report["fault"] else ""),
        "See the docstring of `experiments/longmemeval_cross_user_disputes.py` for the design",
        "and decision rule.",
        "",
        "| Rule | Check | Held in | Needed | Holds |",
        "| --- | --- | --- | --- | --- |",
    ]
    rows = (
        (1, "Determinism: H and H2 identical", "every trial"),
        (2, "Detection: W shows one open dispute, older vs newer, real text", "every trial"),
        (3, "Power: V (visible hidden claims) differs from W", "at least 50%"),
        (4, "A reply counts as knowing the newer claim", "every trial"),
        (5, "Presence alone is only access (bob, dana)", "every trial"),
        (6, "Noninterference: H equals W for every audience", "every trial"),
    )
    for number, text, needed in rows:
        name = RULES[number]
        lines.append("| {} | {} | {} | {} | {} |".format(
            number, text, _share(checks[name]["held"], trials), needed,
            "yes" if decision["rule_{}_{}".format(number, name)] else "no"))
    lines += [
        "",
        "Verdict: **{}**".format(decision["verdict"]),
        "",
        "Reported, not part of the verdict:",
        "",
        "- Hidden claims: {}; restating a visible text word for word: {}.".format(
            summary["hidden_claims"], _share(summary["hidden_restating"], summary["hidden_claims"])),
        "- In V the dispute was closed in {} (in {} of the trials with a claim by dana); "
        "statuses then shown: {}.".format(
            _share(summary["v_closed"], trials),
            _share(summary["v_closed_with_dana"], summary["trials_with_dana"]),
            ", ".join(summary["v_closed_statuses"]) or "-"),
    ]
    if checks["detection"]["held"] == trials:
        lines.append("- In W no dispute closed on its own: two members' claims of equal standing "
                     "stayed disputed, whichever was said later.")
    if report.get("validation"):
        check = report["validation"]
        lines += ["", "Fault validation: rule 6 failed in {}; needed at least {:.0f}%: {}.".format(
            _share(check["failed"], check["trials"]), 100 * FAULT_SHARE,
            "detected" if check["detected"] else "NOT detected")]
    if summary["failures"]:
        lines += ["", "First noninterference failures:", ""]
        lines += ["- {}: {}".format(f["trial"], "; ".join(f["differs"])) for f in summary["failures"]]
    lines += [
        "",
        "Limits: who said which turn is staged; values are compared as exact text, so",
        "paraphrased restatements are not tested.",
        "",
    ]
    return "\n".join(lines)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data", type=Path, default=DATA)
    parser.add_argument("--annotations", type=Path, default=ANNOTATIONS)
    parser.add_argument("--reps", type=int, default=DEFAULT_REPS)
    parser.add_argument("--fault", choices=["administrative"])
    parser.add_argument("--output", type=Path,
                        default=ROOT / "experiments" / "results" / "longmemeval_cross_user_disputes")
    arguments = parser.parse_args(argv)
    annotations = json.loads(arguments.annotations.read_text(encoding="utf-8"))["annotations"]
    questions = json.loads(arguments.data.read_text(encoding="utf-8"))
    pairs, counts = make_pairs(questions, annotations)
    del questions
    restore = (MemoryStore.disputes, MemoryStore.who_knows)
    try:
        if arguments.fault:
            install_fault(arguments.fault)
        trials = [run_trial(pair, index, rep)
                  for index, pair in enumerate(pairs) for rep in range(arguments.reps)]
    finally:
        MemoryStore.disputes, MemoryStore.who_knows = restore
    summary = summarise(trials)
    report = {
        "trials": len(trials), "reps": arguments.reps, "pairs": counts,
        "store_schema_version": SCHEMA_VERSION, "fault": arguments.fault,
        "summary": summary, "decision": decide(summary, len(trials)),
        "data_sha256": sha256(arguments.data), "annotations_sha256": sha256(arguments.annotations),
    }
    if arguments.fault:
        report["validation"] = validate_fault(summary, len(trials))
    text = render(report)
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.with_suffix(".json").write_text(json.dumps(report, indent=2) + "\n")
    arguments.output.with_suffix(".md").write_text(text)
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
