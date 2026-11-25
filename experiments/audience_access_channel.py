"""Does reading leave a trace another member can see? (the record_access side channel)

Question. ``search`` records each read by default: it adds 1 to the
``access_count`` of every memory it returns and sets its ``last_accessed_at``.
Those counters belong to the memory, not to the reader, so everyone who can see
the memory sees them change. ``prune`` also uses them, so reads decide which
memories later disappear for everybody. The access rules (section 7 of
docs/multi_user_memory_review.md) are about what a read *returns*; this
experiment asks what a read *changes* for someone else. Listed as untested in
the earlier reports.

Data. Scripted and synthetic, no LLM. Each trial is built from seed s.
Channels: ``team`` (alice, bob), ``solo`` (alice), ``other`` (carol).
Eight topics, each with a unique token "t<k>tok". ``team`` holds 5 memories per
topic plus 8 memories with no topic token; ``solo`` and ``other`` hold 1 memory
per topic. Memories have importance 0.5 and confidence 0.8. The store clock is a
settable counter (a day count plus one microsecond per call), so reads and
pruning can be placed in time.

Trial. The reader is alice. Her topic t* is drawn from the seed. At day 150 she
runs ``search("t<t*>tok", limit=5, viewers=["alice"])``. At day 200 an
administrator runs ``prune(dry_run=False, as_of=day 200)`` with default
settings: a team memory that nobody read has score about 0.043 and is archived
(below 0.1); one that alice's read touched at day 150 has score about 0.27 and
survives.

Conditions, each a separate store built identically:
- default: alice's search with ``record_access`` left out;
- opt-in: the same search with ``record_access=True``;
- silent: the same search with ``record_access=False``;
- none: alice does not search.
In run 1 (store before the fix, reports in
``experiments/results/audience_access_channel_run1_superseded/``) "default" recorded
the access; there was no opt-in condition because opting in was the default. The
store now makes a read for named viewers silent unless ``record_access=True``, and
this run measures the fix (run 2).

Observers (they read only with ``record_access=False``, so they leave no trace).
- bob (member of ``team`` only) reads ``list_memories`` before and after alice's
  search, and again after the prune. His changed set is the team memories whose
  (access_count, last_accessed_at) differ; his survivor set is the team memories
  still active after the prune.
- carol (member of ``other`` only) does the same for her own memories.
- bob's guess of t*: the topic whose team memories overlap his changed set (or,
  second, his survivor set) the most; a tie is broken at random with the
  trial's own generator, so a guess is correct with probability 1/ties.

Checks, per trial.
1. Determinism (control): the trial run twice gives the same result.
2. Observer control: in the silent and none conditions, bob's changed set is
   empty and every team memory is archived after the prune (survivors none).
3. Ranking: in the default and in the opt-in condition, for each of the 8 topic
   queries, bob's ranked results (memories, order, scores, links) before and
   after alice's search are identical.
4. Hidden: in the default and in the opt-in condition, carol's view (memories
   and counters) is identical before and after alice's search and none of her
   memories survives the prune (she read nothing and nobody read hers); and
   none of bob's changed memories is outside ``team``.
5. Trace: in the default condition bob's changed set is empty and none of his
   team memories survives the prune.

Rules 1, 2 are controls. Rules 3, 4 are the access guarantees this
experiment can confirm, even when a reader opts in. Rule 5 is the question for
the default: it holds only if a read leaves nothing another member can observe.

Decision rule, fixed before running:
  Verdict "inconclusive (control <n> failed)" if rule 1 or 2 fails in any trial.
  Otherwise, if rules 3 and 4 hold in every trial:
    if rule 5 fails: "reads leave a trace other members can see" with the guess
    accuracy of the default;
    if rule 5 holds and bob can still name the topic after an opt-in read in any
    trial: "reads leave no trace by default; opting in still does" with that
    count;
    otherwise "reads leave no trace".
  If rule 3 or 4 fails in any trial: "a read changes what others can observe
  beyond the memories it returned (rules <list> failed, first failing seed
  <s>)".

Reported, not part of the verdict, for the default and for the opt-in condition
separately: how often bob detects that someone read (any change) from counters
and from survivors; bob's accuracy at naming the topic, from counters and from
survivors, with a 95% Wilson interval, against chance (1/8); and, for opt-in,
how often the changed set holds exactly the memories alice's search returned that
bob can see and shows alice's read time (last_accessed_at equal to day 150).

Validation (positive controls against the store), fixed before running; each
fault is put into the store one at a time:
  record-foreign (a search also records access on matching memories outside the
    reader's view, whatever ``record_access`` says unless it is False): rule 4
    fails in at least 95% of trials.
  popularity-boost (the lexical score is multiplied by 1 + 0.5 * access_count):
    rule 3 fails in at least 95% of trials (through the opt-in condition, since
    default reads change no counter).

Default: 500 trials (seeds 0 to 499).

Run from the project root:

    python3 -I experiments/audience_access_channel.py
    python3 -I experiments/audience_access_channel.py --fault record-foreign \\
        --output experiments/results/audience_access_channel_fault_record_foreign
"""

from __future__ import annotations

import argparse
import itertools
import json
import math
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from dynmemory import MemoryStore, MemoryType  # noqa: E402
from dynmemory.store import SCHEMA_VERSION  # noqa: E402

TOPICS = 8
PER_TOPIC = 5
NOISE = 8
READ_DAY, PRUNE_DAY = 150, 200
BIG = 100000
DEFAULT_TRIALS = 500
CHECKS = ("determinism", "observer", "ranking", "hidden", "trace")
RULES = {number: name for number, name in enumerate(CHECKS, start=1)}
CONTROL_RULES = (1, 2)
GUARANTEE_RULES = (3, 4)
FAULTS = ("record-foreign", "popularity-boost")
FAULT_RULE = {"record-foreign": 4, "popularity-boost": 3}
FAULT_SHARE = 0.95
BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)


class Clock:
    def __init__(self):
        self.days = 0
        self.ticks = itertools.count()

    def __call__(self) -> str:
        moment = BASE + timedelta(days=self.days, microseconds=next(self.ticks))
        return moment.isoformat(timespec="microseconds")

    def at(self, days: int) -> datetime:
        return BASE + timedelta(days=days)


def make_trial(seed: int) -> dict:
    rng = random.Random("access-{}".format(seed))
    return {"seed": seed, "topic": rng.randrange(TOPICS)}


def topic_token(topic: int) -> str:
    return "t{}tok".format(topic)


def build(clock: Clock) -> tuple:
    store = MemoryStore(":memory:")
    for member, channel in (("alice", "team"), ("bob", "team"), ("alice", "solo"),
                            ("carol", "other")):
        store.join_channel(channel, member)
    team = {topic: [] for topic in range(TOPICS)}
    noise = []
    writer = store.for_writer("alice")
    for topic in range(TOPICS):
        for number in range(PER_TOPIC):
            team[topic].append(writer.add_memory(
                "{} note{} about the shared plan".format(topic_token(topic), number),
                MemoryType.FACT, channel="team").id)
        writer.add_memory("{} private memo".format(topic_token(topic)),
                          MemoryType.FACT, channel="solo")
        store.for_writer("carol").add_memory(
            "{} carol memo".format(topic_token(topic)), MemoryType.FACT, channel="other")
    for number in range(NOISE):
        noise.append(writer.add_memory(
            "unrelated item {} about the budget".format(number), MemoryType.FACT,
            channel="team").id)
    return store, team, noise


def state(store: MemoryStore, member: str) -> dict:
    return {m.id: (m.access_count, m.last_accessed_at)
            for m in store.list_memories(limit=BIG, viewers=[member], include_archived=False)}


def changed(before: dict, after: dict) -> set:
    return {i for i in after if i in before and after[i] != before[i]}


def ranking(store: MemoryStore, member: str) -> list:
    panel = []
    for topic in range(TOPICS):
        results = store.search(topic_token(topic), limit=10, viewers=[member], record_access=False)
        panel.append([
            (r.memory.id, round(r.score, 12), round(r.lexical_score, 12), r.matched_by,
             tuple((l.source_id, l.target_id, l.relation.value) for l in r.links))
            for r in results
        ])
    return panel


def guess(observed: set, team: dict, rng: random.Random):
    overlaps = {topic: len(observed & set(ids)) for topic, ids in team.items()}
    best = max(overlaps.values())
    if best == 0:
        return None, 0
    tied = [topic for topic, value in overlaps.items() if value == best]
    return rng.choice(tied), len(tied)


import contextlib  # noqa: E402


@contextlib.contextmanager
def fault(name):
    if name is None:
        yield
        return
    if name == "record-foreign":
        original = MemoryStore.search

        def search(self, query, **options):
            results = original(self, query, **options)
            if options.get("record_access", True) and options.get("viewers") is not None:
                original(self, query, limit=BIG, record_access=True)
            return results

        with mock.patch.object(MemoryStore, "search", search):
            yield
    elif name == "popularity-boost":
        original = MemoryStore._lexical_scores

        def boosted(self, active_memories, query_tokens):
            scores, coverage = original(self, active_memories, query_tokens)
            return ({i: v * (1 + 0.5 * active_memories[i].access_count)
                     for i, v in scores.items()}, coverage)

        with mock.patch.object(MemoryStore, "_lexical_scores", boosted):
            yield
    else:
        raise ValueError("unknown fault")


def play(trial: dict, condition: str, flaw=None) -> dict:
    clock = Clock()
    with mock.patch.object(MemoryStore, "_now", staticmethod(clock)), fault(flaw):
        store, team, noise = build(clock)
        team_ids = {i for ids in team.values() for i in ids}
        bob_before, carol_before = state(store, "bob"), state(store, "carol")
        rank_before = ranking(store, "bob")
        clock.days = READ_DAY
        returned = []
        if condition != "none":
            options = {} if condition == "default" else {"record_access": condition == "optin"}
            results = store.search(topic_token(trial["topic"]), limit=5, viewers=["alice"], **options)
            returned = [r.memory.id for r in results]
        bob_after, carol_after = state(store, "bob"), state(store, "carol")
        rank_after = ranking(store, "bob")
        clock.days = PRUNE_DAY
        store.prune(dry_run=False, as_of=clock.at(PRUNE_DAY))
        survivors_bob = set(state(store, "bob")) & team_ids
        survivors_carol = set(state(store, "carol"))
        store.close()
    moved = changed(bob_before, bob_after)
    stamp = clock.at(READ_DAY).strftime("%Y-%m-%d")
    return {
        "changed": moved, "team": team, "team_ids": team_ids,
        "carol_same": carol_before == carol_after, "survivors_carol": survivors_carol,
        "ranking_same": rank_before == rank_after, "survivors": survivors_bob,
        "returned_visible": {i for i in returned if i in team_ids},
        "time_visible": bool(moved) and all(
            (bob_after[i][1] or "").startswith(stamp) for i in moved),
    }


def run(trial: dict, flaw=None) -> dict:
    default, optin, silent, none = (
        play(trial, c, flaw) for c in ("default", "optin", "silent", "none"))
    rng = random.Random("guess-{}".format(trial["seed"]))
    by_counters, _ = guess(default["changed"], default["team"], rng)
    by_prune, _ = guess(default["survivors"], default["team"], rng)
    opt_counters, _ = guess(optin["changed"], optin["team"], rng)
    opt_prune, _ = guess(optin["survivors"], optin["team"], rng)
    quiet = (silent, none)
    return {
        "seed": trial["seed"],
        "observer": all(not q["changed"] and not q["survivors"] and not q["survivors_carol"]
                        and q["carol_same"] and q["ranking_same"] for q in quiet),
        "ranking": default["ranking_same"] and optin["ranking_same"],
        "hidden": all(c["carol_same"] and not c["survivors_carol"]
                      and c["changed"] <= c["team_ids"] for c in (default, optin)),
        "trace": not default["changed"] and not default["survivors"],
        "detected_counters": bool(default["changed"]),
        "detected_prune": bool(default["survivors"]),
        "right_counters": by_counters == trial["topic"],
        "right_prune": by_prune == trial["topic"],
        "optin_detected_counters": bool(optin["changed"]),
        "optin_detected_prune": bool(optin["survivors"]),
        "optin_right_counters": opt_counters == trial["topic"],
        "optin_right_prune": opt_prune == trial["topic"],
        "exact": optin["changed"] == optin["returned_visible"],
        "time_visible": optin["time_visible"],
    }


def run_trial(seed: int, flaw=None) -> dict:
    trial = make_trial(seed)
    first, second = run(trial, flaw), run(trial, flaw)
    result = dict(first)
    result["determinism"] = first == second
    return result


# --- summary, decision, report ----------------------------------------------------------


def wilson(count: int, total: int) -> tuple:
    if not total:
        return 0.0, 0.0
    z, p = 1.959964, count / total
    centre = (p + z * z / (2 * total)) / (1 + z * z / total)
    half = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / (1 + z * z / total)
    return centre - half, centre + half


def summarise(trials: list) -> dict:
    checks = {
        name: {"held": sum(bool(t[name]) for t in trials),
               "not_held_seeds": [t["seed"] for t in trials if not t[name]]}
        for name in CHECKS
    }
    count = len(trials)
    rates = {name: sum(bool(t[name]) for t in trials) for name in
             ("detected_counters", "detected_prune", "right_counters", "right_prune",
              "optin_detected_counters", "optin_detected_prune", "optin_right_counters",
              "optin_right_prune", "exact", "time_visible")}
    return {"checks": checks, "rates": rates,
            "intervals": {name: wilson(value, count) for name, value in rates.items()}}


def decide(summary: dict, trials: int) -> dict:
    checks = summary["checks"]
    holds_ = {n: checks[name]["held"] == trials for n, name in RULES.items()}
    failed_controls = [n for n in CONTROL_RULES if not holds_[n]]
    failed_guarantees = [n for n in GUARANTEE_RULES if not holds_[n]]
    if failed_controls:
        verdict = "inconclusive (control {} failed)".format(", ".join(map(str, failed_controls)))
    elif failed_guarantees:
        seeds = [s for n in failed_guarantees for s in checks[RULES[n]]["not_held_seeds"]]
        verdict = ("a read changes what others can observe beyond the memories it returned "
                   "(rules {} failed, first failing seed {})".format(
                       ", ".join(map(str, failed_guarantees)), min(seeds)))
    elif holds_[5]:
        opted = summary["rates"].get("optin_right_counters", 0)
        verdict = ("reads leave no trace by default; opting in still does (topic named from counters "
                   "in {} of {} trials)".format(opted, trials) if opted else "reads leave no trace")
    else:
        rates = summary["rates"]
        verdict = ("reads leave a trace other members can see (topic named from counters in "
                   "{} of {} trials; chance {:.1%})".format(
                       rates["right_counters"], trials, 1.0 / TOPICS))
    decision = {"rule_{}_{}".format(n, name): holds_[n] for n, name in RULES.items()}
    decision["verdict"] = verdict
    return decision


def validate_fault(flaw: str, trials: list) -> dict:
    name = RULES[FAULT_RULE[flaw]]
    failed = sum(not t[name] for t in trials)
    share = failed / len(trials)
    return {"fault": flaw, "rule": FAULT_RULE[flaw], "failed": failed, "trials": len(trials),
            "share": share, "detected": share >= FAULT_SHARE}


def _share(count: int, total: int) -> str:
    low, high = wilson(count, total)
    return "{} of {} ({:.1f}%, 95% interval {:.1f} to {:.1f}%)".format(
        count, total, 100.0 * count / total, 100 * low, 100 * high)


def render(report: dict) -> str:
    trials, summary, decision = report["trials"], report["summary"], report["decision"]
    checks, rates = summary["checks"], summary["rates"]
    lines = [
        "# The record_access side channel",
        "",
        "Synthetic, scripted data; no LLM. {} trials (seeds 0 to {}); {} topics, chance {:.1%}.".format(
            trials, trials - 1, TOPICS, 1.0 / TOPICS),
        "Store under test: schema version {}{}.".format(
            report["store_schema_version"],
            "; injected fault: {}".format(report["fault"]) if report.get("fault") else ""),
        "See the docstring of `experiments/audience_access_channel.py` for the design and rule.",
        "",
        "| Rule | Check | Held in | Needed | Holds |",
        "| --- | --- | --- | --- | --- |",
    ]
    rows = (
        (1, "Determinism: the same seed gives the same result (control)"),
        (2, "Observer control: with a silent read or none, the observer sees no change (control)"),
        (3, "Ranking: another member's ranked results are unchanged by a read"),
        (4, "Hidden: a member of another channel sees no change; nothing outside the channel changes"),
        (5, "Trace: another member of the channel sees no change after a read"),
    )
    for number, text in rows:
        name = RULES[number]
        lines.append("| {} | {} | {} | every trial | {} |".format(
            number, text, _share(checks[name]["held"], trials),
            decision["rule_{}_{}".format(number, name)]))
    lines += [
        "",
        "**Verdict: {}**".format(decision["verdict"]),
        "",
        "Reported, not part of the verdict (the observer is bob, a member of `team` who did not read):",
        "",
        "- Default read (`record_access` left out). Sees that someone read, from the counters: {}; from"
        " the survivors of a later prune: {}. Names alice's topic from the counters: {}; from the survivors: {}.".format(
            _share(rates["detected_counters"], trials), _share(rates["detected_prune"], trials),
            _share(rates["right_counters"], trials), _share(rates["right_prune"], trials)),
        "- Opt-in read (`record_access=True`). Sees that someone read, from the counters: {}; from the"
        " survivors: {}. Names alice's topic from the counters: {}; from the survivors: {}.".format(
            _share(rates["optin_detected_counters"], trials), _share(rates["optin_detected_prune"], trials),
            _share(rates["optin_right_counters"], trials), _share(rates["optin_right_prune"], trials)),
        "- Opt-in: changed set equals exactly the returned memories bob can see: {}; shows the read's time"
        " (last_accessed_at on every changed memory): {}.".format(
            _share(rates["exact"], trials), _share(rates["time_visible"], trials)),
        "",
        "Limits: one reader, one query, and unique topic tokens, which is the easy case for an"
        " observer. The counters belong to the memory, so a reader who opts in with"
        " `record_access=True` (the CLI's `--record`) still tells every member who can see it what"
        " they looked up; the server does not let members opt in. With the default, reads for named"
        " viewers no longer count as accesses, so they no longer keep a memory from being pruned;"
        " retention then depends on reads without viewers, or on opted-in reads.",
        "",
    ]
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--trials", type=int, default=DEFAULT_TRIALS)
    parser.add_argument("--fault", choices=FAULTS)
    parser.add_argument(
        "--output", type=Path, default=ROOT / "experiments" / "results" / "audience_access_channel")
    arguments = parser.parse_args(argv)
    if arguments.trials < 1:
        parser.error("--trials must be positive")
    trials = [run_trial(seed, arguments.fault) for seed in range(arguments.trials)]
    summary = summarise(trials)
    report = {
        "trials": arguments.trials, "fault": arguments.fault,
        "store_schema_version": SCHEMA_VERSION, "summary": summary,
        "decision": decide(summary, arguments.trials),
        "validation": validate_fault(arguments.fault, trials) if arguments.fault else None,
    }
    text = render(report)
    if report["validation"]:
        v = report["validation"]
        text += "\nValidation: rule {} failed in {} of {} trials ({:.1f}%): {}.\n".format(
            v["rule"], v["failed"], v["trials"], 100 * v["share"],
            "detected" if v["detected"] else "NOT detected")
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.with_suffix(".json").write_text(json.dumps(report, indent=2) + "\n")
    arguments.output.with_suffix(".md").write_text(text)
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
