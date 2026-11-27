"""Zero leakage at no utility cost: does filtering before retrieval cost a viewer answers?

Question (H1 in section 9 of docs/multi_user_memory_review.md). Does filtering
before retrieval, as built (``search(..., viewers=...)``), give zero leakage at
no utility cost, compared with filtering after retrieval? The review lists a
fourth arm, filtering before retrieval plus per-audience summaries. It does not
apply here: Memvane has no consolidation, so there are no summaries to build
per audience.

Data. Scripted and synthetic, no LLM, no real text. Each trial builds one
workspace in one store:
- Members ana, ben, cy, dee, eli and fay. Channel ``general`` holds all six;
  ``p1``, ``p2`` and ``p3`` each hold a random subset of 2, 3 or 4 members
  (size drawn uniformly). Memberships do not change during a trial.
- 25 pseudo-word subjects (sub00 to sub24) and eight attributes (deadline,
  budget, owner, venue, status, vendor, risk, metric). Values are pseudo-words
  (val000 to val199); filler words come from a separate vocabulary of 200
  (fil000 to fil199). No word belongs to two vocabularies.
- Facts: 40 in ``general`` and 30 in each private channel. Each takes a
  (subject, attribute) pair drawn at random with replacement, so a pair can
  recur within a channel and across channels, with different values. Its text
  is "The {attribute} of {subject} is {value}." followed by 0 to 6 filler
  words; its kind is ``fact`` and its speaker a random member of the channel.
- Canaries: 5 per channel, ``general`` included, written exactly like facts
  (same template, same 0 to 6 filler words) but with the unique value
  ``canary<seed>x<k>``, k = 0 to 19 within the trial. The speaker is a random
  member of the channel and is the canary's owner.
- 150 memories in all, written in one random order. Equal scores rank the
  newer memory first, so writing channel by channel would let one channel win
  every tie. No links, no keys, lexical search only (no embedder), k = 10.
Workspace draws come from ``Random("<seed>-workspace")`` and question draws
from ``Random("<seed>-questions")``. Memory IDs are mapped to labels assigned
at writing ("p2/fact07", "general/canary3"); an ID with no label would show as
"?" + ID. Nothing reported depends on IDs or on wall-clock time.

Questions. The query for a (subject, attribute) pair is "{attribute}
{subject}". Each member is a viewer on their own (``viewers`` names one
member). A memory is visible to a viewer if they belong to its channel; the
after arms and every statistic decide this from the experiment's own record of
channels and memberships, never from the store's ``viewers`` code.
- Utility: per viewer, 20 pairs drawn without replacement from the pairs that
  have at least one memory visible to that viewer. Gold is every memory
  visible to the viewer with that pair, canaries included. Scores: the
  reciprocal rank (RR) of the first gold memory among the first k results
  shown (0 if none), and hit@k. Gold does not depend on the arm, so the pooled
  arm is scored against what the viewer may see.
- Leakage: for each viewer and each canary in a private channel the viewer is
  not in, the viewer asks the canary's query. A leak: the canary is among the
  first k results the viewer is shown.
- Owner: for each canary in a private channel, its owner asks its query. A
  hit: the canary is among the first k results shown.
- Over-blocking: for each ``general`` canary and each of the six members, the
  member asks its query in the built arm with ``limit=1000``. The canary must
  be returned; hit@k (within the first k of that list) is also reported.

Arms (BIG = 1000, more than the 150 memories in the store; every read passes
``record_access=False``).
- pooled: ``search(q, limit=BIG)``, unfiltered, first k: one shared store with
  no access control.
- after-k: ``search(q, limit=k)``, then the results the viewer cannot see are
  dropped. This is the naive version and can show fewer than k results.
- after-all: ``search(q, limit=BIG)``, drop what the viewer cannot see, then
  take the first k.
- built: ``search(q, limit=k, viewers=viewer)``.
All four read the same store, and reads do not change it, so each distinct
call is made once per trial and its result is shared by the arms and viewers
that make the same call (pooled and after-all both call
``search(q, limit=BIG)``).

Controls.
- Positive: the pooled arm must leak canaries, or a clean filtered arm means
  nothing; and owners must find their own canaries in the built arm, or a
  clean built arm could simply be returning too little.
- Negative (no over-blocking): a canary in ``general`` must be returned to
  every member by the built arm.
- Sanity, reported: every store held at most BIG memories, so after-all saw
  the whole ranking; and write timestamps rose strictly in write order, so
  equal scores were ordered by write order and never by random IDs.

Decision rule, fixed before running:
  1. Positive controls: pooled leaks in at least 50% of leakage items, pooled
     over all trials; and the owner hit@k in the built arm is at least 95%.
  2. Negative control: every over-blocking item is returned by the built arm,
     in every trial (100%).
  3. Zero leakage: built, after-k and after-all leak in 0 leakage items in
     every trial.
  4. Utility: D = the per-trial mean RR of built minus that of after-all, over
     the utility items. Take the mean of D over trials and a 95% percentile
     bootstrap CI over trials (2,000 resamples drawn with ``Random(0)``; the
     bounds are the 51st and 1,950th of the sorted resampled means, as in
     ``longmemeval_knowledge_update.py``). The reading is "no utility cost" if
     the CI's lower bound is at least -0.01, "utility cost" if its upper bound
     is below -0.01, and "unclear" otherwise. Built minus after-k and built
     minus pooled are reported the same way (each with a fresh ``Random(0)``),
     descriptively, with hit@k and the mean number of results shown per arm.
Verdict: "inconclusive (a control failed)" if rule 1 or 2 fails; otherwise
"H1 supported" if rule 3 holds and rule 4 reads "no utility cost"; otherwise
"H1 not supported: <reasons>".

Run from the project root (200 trials by default):

    python3 -I experiments/audience_utility.py

Harder workload (``--hard``), written 2026-11-27 before any hard run.

Why. In the workload above, gold memories are the only memories that hold
both query words, so every filtered arm reached RR 1.0 in every trial and
rule 4 could not see a ranking cost. The built path computes its BM25
statistics (inverse document frequency, average length) over the memories the
viewers may see, not over the whole store, so it can order the same visible
memories differently from after-all. The hard workload makes that order
matter. The default workload, its options and its report are unchanged.

Hypothesis (H1, hard). With distractors that share query words, graded
relevance and audiences of one to three people, searching with ``viewers``
gives zero leakage and costs no more than 0.01 on any utility metric against
filtering after ranking the whole store (after-all).

Data. Scripted and synthetic as above; workspace draws from
``Random("<seed>-hard-workspace")``, question draws from
``Random("<seed>-hard-questions")``.
- Members as above. ``general`` holds all six; ``p1``, ``p2`` and ``p3`` each
  hold a random subset of 1 to 5 members (size drawn uniformly).
- 12 subjects (sub00 to sub11) and 12 attributes (the eight above plus scope,
  quota, region and sponsor), so every query word is common. Values and
  filler as above. Template words (the, of, is, noted, and, in, passing,
  report, sync, notes, unaffected) belong to no other vocabulary.
- Each memory's channel is drawn with weights general 2, p1, p2 and p3 1 each
  (canaries excepted), and its speaker is a random member of that channel.
- 8 focus pairs (subject s, attribute a), drawn without replacement from the
  144 pairs. Per focus pair:
  - 3 to 6 answers, "The {a} of {s} is {value}." plus 0 to 20 filler words;
  - 2 to 4 mentions, "Noted {s} and {a} in passing." plus 0 to 20 filler;
  - 3 attribute-heavy distractors, "{a} ... report: The {a} of {s2} is
    {value}." with the leading {a} written 1 to 3 times, s2 != s, 0 to 2 filler;
  - 3 subject-heavy distractors, "{s} ... sync notes: The {a2} of {s} is
    {value}." with the leading {s} written 1 to 3 times, a2 != a, 0 to 2 filler;
  - 2 decoys holding both query words, "The {a} of {s2} is {value}; {s}
    unaffected." with s2 != s, 0 to 2 filler.
- 40 background facts, "The {a} of {s} is {value}." for a random pair, plus 0
  to 12 filler words.
- 3 canaries per channel, "The {a} of {s} is canary<seed>h<k>." for a random
  pair, plus 0 to 12 filler words, k = 0 to 11; the speaker owns it.
- All memories (about 180) written in one random order; no links, no keys,
  lexical search only, k = 10.
Grades. Every memory records one (subject, attribute) pair and a form
(answer, mention or canary; distractors, decoys and background facts are
answers for their own pair). For the query of pair (s, a) a memory has grade
2 if it is an answer or canary for (s, a), grade 1 if it is a mention of
(s, a), and 0 otherwise. Repeated words, a decoy's second subject and
template words never change a grade, so distractors and decoys are grade 0
for the focus pair although they share one or both of its query words.

Questions. An audience sees a memory if every one of its members belongs to
the memory's channel (the store's rule, decided from the experiment's record).
Audiences: each member alone, and six groups drawn with ``rng.sample``, three
of two members and three of three (a group may repeat).
- Utility: each audience asks "{a} {s}" for each focus pair of which it can
  see at least one grade-2 memory. Gold: the grades of the memories it sees.
- Ceiling: each focus pair asked once with no audience; gold is every memory
  of grade 1 or 2 in the store, whatever its channel.
- Leakage: each audience asks, for each canary in a private channel it cannot
  see, "{a} {s} {canary value}". The value is in that canary alone, so pooled
  ranks it first and the positive control is strong.
- Owner: each private canary's speaker asks the same query alone.
- Over-blocking: each audience asks each ``general`` canary's query in the
  built arm with ``limit=1000``.

Arms. pooled, after-k, after-all and built as above, with ``viewers`` set to
the audience. Two planted faults, computed for every utility item as controls
that degrade the built arm only (they never reach leakage, owner or
over-blocking items):
- fault-drop-term: the built search with the query's rarest word removed (the
  word the fewest memories of the trial contain, ties to the alphabetically
  first);
- fault-swap-top: the built results with the first two swapped.
``--fault NAME`` also puts that fault in place of the built arm of every
utility item (a simulated broken store), which must turn the verdict.

Metrics, per utility item and arm, on the first k = 10 shown.
- nDCG@10 (primary): gain 2^grade - 1, discount 1 / log2(rank + 1), divided by
  the DCG of the audience's visible grades sorted from high to low.
- RR: reciprocal rank of the first grade-2 memory, 0 if none is shown.
- recall@3: the share of the audience's visible memories of grade 1 or 2 that
  are among the first 3 shown (below 1 whenever more than 3 are visible).
- Descriptive: hit@k (a grade-2 memory shown), mean results shown, and the
  share of items where built and after-all show the same list.

Decision rule (hard), fixed before running.
  1. Positive controls: pooled leaks in at least 50% of leakage items; owner
     hit@k in the built arm at least 95%.
  2. Negative control: every over-blocking item is returned (100%).
  3. Ceiling control: the pooled arm's mean RR over the ceiling items of a
     trial is below 1.0 in at least 95% of trials; at least 20% of ceiling
     items have RR below 1.0; and at least 20% of utility items have an
     after-all nDCG@10 below 1.0.
  4. Fault control: for each fault arm, D on nDCG@10 (fault arm minus
     after-all, computed as in rule 7) reads "utility cost".
  5. Determinism: the trials for seeds 0 to min(2, trials - 1), run again from
     scratch, equal the first run (items and scores).
  6. Zero leakage: after-k, after-all and built leak in 0 leakage items.
  7. Utility, for nDCG@10, RR and recall@3 separately: D = the per-trial mean
     of built minus that of after-all over the utility items (paired: both
     arms answer the same items). Mean of D over trials and a 95% percentile
     bootstrap CI over trials, drawn exactly as in rule 4 (a fresh
     ``Random(0)`` per comparison). Reading: "no utility cost" if the lower
     bound is at least -0.01, "utility cost" if the upper bound is below
     -0.01, "unclear" otherwise. Reported, not decisive: "equal within the
     margin" if the whole CI lies in [-0.01, +0.01]; "difference detected"
     if the CI excludes 0; an exact two-sided sign test over trials (higher
     against lower, ties dropped); and item-level higher / equal / lower.
     Built minus after-k and built minus pooled are reported the same way.
Verdict: "inconclusive (a control failed)" if rule 1, 2, 3, 4 or 5 fails;
otherwise "H1 supported" if rule 6 holds and all three metrics read "no
utility cost"; otherwise "H1 not supported: <reasons>".

    python3 -I experiments/audience_utility.py --hard --output <path>
    python3 -I experiments/audience_utility.py --hard --fault fault-swap-top --output <path>
"""

from __future__ import annotations

import argparse
import json
import math
import random
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from dynmemory import MemoryStore, MemoryType  # noqa: E402

MEMBERS = ("ana", "ben", "cy", "dee", "eli", "fay")
GENERAL = "general"
PRIVATE_CHANNELS = ("p1", "p2", "p3")
CHANNELS = (GENERAL,) + PRIVATE_CHANNELS
PRIVATE_SIZES = (2, 3, 4)
SUBJECTS = tuple("sub{:02d}".format(index) for index in range(25))
ATTRIBUTES = (
    "deadline",
    "budget",
    "owner",
    "venue",
    "status",
    "vendor",
    "risk",
    "metric",
)
VALUES = tuple("val{:03d}".format(index) for index in range(200))
FILLER = tuple("fil{:03d}".format(index) for index in range(200))
MAX_FILLER_WORDS = 6
FACTS_PER_CHANNEL = {GENERAL: 40, "p1": 30, "p2": 30, "p3": 30}
CANARIES_PER_CHANNEL = 5
K = 10
BIG = 1000
UTILITY_PAIRS_PER_VIEWER = 20
BOOTSTRAP_SAMPLES = 2000
BOOTSTRAP_SEED = 0
UTILITY_MARGIN = 0.01
POOLED_LEAK_SHARE = 0.5
OWNER_HIT_SHARE = 0.95
ZERO = 1e-12
DEFAULT_TRIALS = 200
ITEM_TYPES = ("utility", "leakage", "owner", "over_blocking")
ARMS = ("pooled", "after-k", "after-all", "built")
FILTERED_ARMS = ("after-k", "after-all", "built")
ARM_LABELS = {
    "pooled": "pooled (no access control)",
    "after-k": "filter after, first k only",
    "after-all": "filter after, whole ranking",
    "built": "search with viewers (built)",
}
# (summary key, arm subtracted from built); the first one is rule 4.
COMPARISONS = (
    ("built_minus_after_all", "after-all"),
    ("built_minus_after_k", "after-k"),
    ("built_minus_pooled", "pooled"),
)


def _content(rng: random.Random, subject: str, attribute: str, value: str) -> str:
    words = [rng.choice(FILLER) for _ in range(rng.randint(0, MAX_FILLER_WORDS))]
    return " ".join(["The {} of {} is {}.".format(attribute, subject, value)] + words)


def build_workspace(seed: int) -> dict:
    """Memberships and memories of one trial, memories in write order."""
    rng = random.Random("{}-workspace".format(seed))
    members = {GENERAL: list(MEMBERS)}
    for channel in PRIVATE_CHANNELS:
        members[channel] = sorted(rng.sample(MEMBERS, rng.choice(PRIVATE_SIZES)))
    memories = []
    canary_number = 0
    for channel in CHANNELS:
        facts = FACTS_PER_CHANNEL[channel]
        for index in range(facts + CANARIES_PER_CHANNEL):
            canary = index >= facts
            subject = rng.choice(SUBJECTS)
            attribute = rng.choice(ATTRIBUTES)
            if canary:
                value = "canary{}x{}".format(seed, canary_number)
                label = "{}/canary{}".format(channel, index - facts)
                canary_number += 1
            else:
                value = rng.choice(VALUES)
                label = "{}/fact{:02d}".format(channel, index)
            memories.append(
                {
                    "label": label,
                    "channel": channel,
                    "subject": subject,
                    "attribute": attribute,
                    "value": value,
                    "canary": canary,
                    "speaker": rng.choice(members[channel]),
                    "content": _content(rng, subject, attribute, value),
                }
            )
    rng.shuffle(memories)
    return {"seed": seed, "members": members, "memories": memories}


def visible_channels(workspace: dict) -> dict:
    """Each member's channels, from the experiment's own record."""
    return {
        member: frozenset(
            channel for channel in CHANNELS if member in workspace["members"][channel]
        )
        for member in MEMBERS
    }


def query_for(memory: dict) -> str:
    return "{} {}".format(memory["attribute"], memory["subject"])


def questions(workspace: dict) -> list:
    """Every question of the trial, before any store exists."""
    rng = random.Random("{}-questions".format(workspace["seed"]))
    channels = visible_channels(workspace)
    memories = workspace["memories"]
    asked = []
    for viewer in MEMBERS:
        visible = [memory for memory in memories if memory["channel"] in channels[viewer]]
        # Sorted, so the draw does not depend on set order.
        pairs = sorted({(memory["subject"], memory["attribute"]) for memory in visible})
        for subject, attribute in rng.sample(
            pairs, min(UTILITY_PAIRS_PER_VIEWER, len(pairs))
        ):
            gold = sorted(
                memory["label"]
                for memory in visible
                if (memory["subject"], memory["attribute"]) == (subject, attribute)
            )
            asked.append(
                {
                    "type": "utility",
                    "viewer": viewer,
                    "query": "{} {}".format(attribute, subject),
                    "gold": gold,
                }
            )
    # Labels sort in the order canaries were drawn: general, p1, p2, p3.
    canaries = sorted(
        (memory for memory in memories if memory["canary"]),
        key=lambda memory: memory["label"],
    )
    private = [canary for canary in canaries if canary["channel"] != GENERAL]
    for viewer in MEMBERS:
        for canary in private:
            if canary["channel"] not in channels[viewer]:
                asked.append(
                    {
                        "type": "leakage",
                        "viewer": viewer,
                        "query": query_for(canary),
                        "canary": canary["label"],
                    }
                )
    for canary in private:
        asked.append(
            {
                "type": "owner",
                "viewer": canary["speaker"],
                "query": query_for(canary),
                "canary": canary["label"],
            }
        )
    for canary in canaries:
        if canary["channel"] == GENERAL:
            for member in MEMBERS:
                asked.append(
                    {
                        "type": "over_blocking",
                        "viewer": member,
                        "query": query_for(canary),
                        "canary": canary["label"],
                    }
                )
    return asked


def populate(store: MemoryStore, workspace: dict) -> tuple:
    """Write the workspace; return the ID-to-label map and the write timestamps."""
    for channel in CHANNELS:
        for member in workspace["members"][channel]:
            store.join_channel(channel, member)
    labels = {}
    stamps = []
    for memory in workspace["memories"]:
        written = store.add_memory(
            memory["content"],
            MemoryType.FACT,
            channel=memory["channel"],
            speaker=memory["speaker"],
        )
        labels[written.id] = memory["label"]
        stamps.append(written.created_at)
    return labels, stamps


def shown_by_arm(read, visible, viewer: str, query: str) -> dict:
    """What the viewer is shown in each arm.

    ``read(query, limit, viewer=None)`` returns the labels of a search, in
    order; ``visible(viewer, label)`` applies the experiment's own record.
    """
    return {
        "pooled": read(query, BIG)[:K],
        "after-k": [label for label in read(query, K) if visible(viewer, label)],
        "after-all": [label for label in read(query, BIG) if visible(viewer, label)][:K],
        "built": list(read(query, K, viewer)),
    }


def answer(store: MemoryStore, labels: dict, workspace: dict, asked: list) -> list:
    """Ask every question in every arm; return the questions with what was shown."""
    channels = visible_channels(workspace)
    channel_of = {memory["label"]: memory["channel"] for memory in workspace["memories"]}
    calls = {}

    def read(query: str, limit: int, viewer=None) -> list:
        key = (query, limit, viewer)
        if key not in calls:
            calls[key] = [
                labels.get(result.memory.id, "?" + result.memory.id)
                for result in store.search(
                    query, limit=limit, record_access=False, viewers=viewer
                )
            ]
        return calls[key]

    def visible(viewer: str, label: str) -> bool:
        # An unlabelled result has no recorded channel and is never visible.
        return channel_of.get(label) in channels[viewer]

    answered = []
    for item in asked:
        if item["type"] == "over_blocking":
            shown = {"built": list(read(item["query"], BIG, item["viewer"]))}
        else:
            shown = shown_by_arm(read, visible, item["viewer"], item["query"])
        answered.append(dict(item, shown=shown))
    return answered


def reciprocal_rank(shown: list, gold: list) -> float:
    for rank, label in enumerate(shown[:K], start=1):
        if label in gold:
            return 1.0 / rank
    return 0.0


def score_items(items: list) -> dict:
    """Per-trial counts and means from the answered questions."""
    by_type = {name: [item for item in items if item["type"] == name] for name in ITEM_TYPES}
    utility = by_type["utility"]
    scores = {"utility": {"items": len(utility), "rr": {}, "hit": {}, "shown": {}}}
    for arm in ARMS:
        ranks = [reciprocal_rank(item["shown"][arm], item["gold"]) for item in utility]
        scores["utility"]["rr"][arm] = sum(ranks) / len(ranks)
        scores["utility"]["hit"][arm] = sum(rank > 0 for rank in ranks) / len(ranks)
        scores["utility"]["shown"][arm] = sum(
            len(item["shown"][arm]) for item in utility
        ) / len(utility)
    for name, field in (("leakage", "leaks"), ("owner", "hits")):
        scores[name] = {
            "items": len(by_type[name]),
            field: {
                arm: sum(item["canary"] in item["shown"][arm][:K] for item in by_type[name])
                for arm in ARMS
            },
        }
    over = by_type["over_blocking"]
    scores["over_blocking"] = {
        "items": len(over),
        "returned": sum(item["canary"] in item["shown"]["built"] for item in over),
        "hit_at_k": sum(item["canary"] in item["shown"]["built"][:K] for item in over),
    }
    return scores


def run_trial(seed: int) -> dict:
    workspace = build_workspace(seed)
    asked = questions(workspace)
    with MemoryStore(":memory:") as store:
        labels, stamps = populate(store, workspace)
        items = answer(store, labels, workspace, asked)
    return {
        "seed": seed,
        "members": {channel: workspace["members"][channel] for channel in PRIVATE_CHANNELS},
        "memories": len(labels),
        "timestamps_increase": all(
            earlier < later for earlier, later in zip(stamps, stamps[1:])
        ),
        "items": items,
        "scores": score_items(items),
    }


def _share(part: float, whole: float):
    return part / whole if whole else None


def _first_seed(trials: list, failed) -> tuple:
    """The lowest seed whose trial failed, and how many trials failed."""
    seeds = [trial["seed"] for trial in trials if failed(trial)]
    return (min(seeds) if seeds else None), len(seeds)


def bootstrap(values: list) -> dict:
    """Mean and 95% percentile bootstrap CI over trials, drawn with ``Random(0)``."""
    rng = random.Random(BOOTSTRAP_SEED)
    means = sorted(
        sum(rng.choice(values) for _ in values) / len(values)
        for _ in range(BOOTSTRAP_SAMPLES)
    )
    return {
        "mean": sum(values) / len(values),
        "ci95": [
            means[int(0.025 * BOOTSTRAP_SAMPLES)],
            means[int(0.975 * BOOTSTRAP_SAMPLES) - 1],
        ],
        "higher": sum(value > ZERO for value in values),
        "equal": sum(abs(value) <= ZERO for value in values),
        "lower": sum(value < -ZERO for value in values),
        "values": values,
    }


def summarise(trials: list) -> dict:
    def total(name: str, field: str, arm: str) -> int:
        return sum(trial["scores"][name][field][arm] for trial in trials)

    leakage_items = sum(trial["scores"]["leakage"]["items"] for trial in trials)
    leakage = {"items": leakage_items, "by_arm": {}}
    for arm in ARMS:
        first, failing = _first_seed(
            trials, lambda trial, arm=arm: trial["scores"]["leakage"]["leaks"][arm] > 0
        )
        leaks = total("leakage", "leaks", arm)
        leakage["by_arm"][arm] = {
            "leaks": leaks,
            "share": _share(leaks, leakage_items),
            "trials_with_leak": failing,
            "first_seed": first,
        }

    owner_items = sum(trial["scores"]["owner"]["items"] for trial in trials)
    owner = {
        "items": owner_items,
        "by_arm": {
            arm: {
                "hits": total("owner", "hits", arm),
                "share": _share(total("owner", "hits", arm), owner_items),
            }
            for arm in ARMS
        },
    }
    owner["built_first_miss_seed"], owner["built_trials_with_miss"] = _first_seed(
        trials,
        lambda trial: trial["scores"]["owner"]["hits"]["built"]
        < trial["scores"]["owner"]["items"],
    )

    over_items = sum(trial["scores"]["over_blocking"]["items"] for trial in trials)
    returned = sum(trial["scores"]["over_blocking"]["returned"] for trial in trials)
    hit_at_k = sum(trial["scores"]["over_blocking"]["hit_at_k"] for trial in trials)
    first, failing = _first_seed(
        trials,
        lambda trial: trial["scores"]["over_blocking"]["returned"]
        < trial["scores"]["over_blocking"]["items"],
    )
    over_blocking = {
        "items": over_items,
        "returned": returned,
        "missing": over_items - returned,
        "hit_at_k": hit_at_k,
        "hit_at_k_share": _share(hit_at_k, over_items),
        "trials_with_missing": failing,
        "first_seed": first,
    }

    per_trial = {
        arm: [trial["scores"]["utility"]["rr"][arm] for trial in trials] for arm in ARMS
    }
    utility = {
        "items": sum(trial["scores"]["utility"]["items"] for trial in trials),
        "by_arm": {
            arm: {
                "mean_rr": sum(per_trial[arm]) / len(trials),
                "hit_at_k": sum(trial["scores"]["utility"]["hit"][arm] for trial in trials)
                / len(trials),
                "mean_shown": sum(
                    trial["scores"]["utility"]["shown"][arm] for trial in trials
                )
                / len(trials),
            }
            for arm in ARMS
        },
        "differences": {
            name: bootstrap(
                [built - other for built, other in zip(per_trial["built"], per_trial[arm])]
            )
            for name, arm in COMPARISONS
        },
    }
    return {
        "trials": len(trials),
        "leakage": leakage,
        "owner": owner,
        "over_blocking": over_blocking,
        "utility": utility,
        "sanity": {
            "most_memories": max(trial["memories"] for trial in trials),
            "big_covers_every_store": all(trial["memories"] <= BIG for trial in trials),
            "timestamps_increase": sum(trial["timestamps_increase"] for trial in trials),
        },
    }


def utility_reading(ci95: list) -> str:
    lower, upper = ci95
    if lower >= -UTILITY_MARGIN:
        return "no utility cost"
    if upper < -UTILITY_MARGIN:
        return "utility cost"
    return "unclear"


def decide(summary: dict, trials: int) -> dict:
    """Apply the decision rule to a summary.

    ``trials`` is the number of trials, kept for the signature the audience
    experiments share; every rule here is a share of items or a count of
    failures, read from the summary.
    """
    leakage = summary["leakage"]
    pooled_share = _share(leakage["by_arm"]["pooled"]["leaks"], leakage["items"])
    pooled_leaks = pooled_share is not None and pooled_share >= POOLED_LEAK_SHARE
    owner_share = _share(
        summary["owner"]["by_arm"]["built"]["hits"], summary["owner"]["items"]
    )
    owner_finds = owner_share is not None and owner_share >= OWNER_HIT_SHARE
    over = summary["over_blocking"]
    no_over_blocking = over["items"] > 0 and over["missing"] == 0
    clean = {arm: leakage["by_arm"][arm]["leaks"] == 0 for arm in FILTERED_ARMS}
    zero_leakage = all(clean.values())
    difference = summary["utility"]["differences"]["built_minus_after_all"]
    reading = utility_reading(difference["ci95"])

    reasons = []
    if not zero_leakage:
        reasons.append(
            "rule 3, leaks in "
            + ", ".join(
                "{} ({} of {} items, first failing seed {})".format(
                    arm,
                    leakage["by_arm"][arm]["leaks"],
                    leakage["items"],
                    leakage["by_arm"][arm]["first_seed"],
                )
                for arm in FILTERED_ARMS
                if not clean[arm]
            )
        )
    if reading != "no utility cost":
        reasons.append(
            "rule 4, {} (built minus after-all {:+.4f}, 95% CI {:+.4f} to {:+.4f})".format(
                "utility cost" if reading == "utility cost" else "utility unclear",
                difference["mean"],
                difference["ci95"][0],
                difference["ci95"][1],
            )
        )
    if not (pooled_leaks and owner_finds and no_over_blocking):
        verdict = "inconclusive (a control failed)"
    elif not reasons:
        verdict = "H1 supported"
    else:
        verdict = "H1 not supported: " + "; ".join(reasons)
    return {
        "rule_1_pooled_leaks": pooled_leaks,
        "rule_1_owner_finds_canary": owner_finds,
        "rule_1_positive_controls_hold": pooled_leaks and owner_finds,
        "rule_2_no_over_blocking": no_over_blocking,
        "rule_3_zero_leakage": zero_leakage,
        "rule_3_zero_leakage_by_arm": clean,
        "rule_4_utility": reading,
        "reasons": reasons,
        "verdict": verdict,
    }


def _percent(part: float, whole: float) -> str:
    return "{:.1%}".format(part / whole) if whole else "n/a"


def render(report: dict) -> str:
    trials = report["trials"]
    summary = report["summary"]
    decision = report["decision"]
    leakage = summary["leakage"]
    owner = summary["owner"]
    over = summary["over_blocking"]
    utility = summary["utility"]
    sanity = summary["sanity"]
    lines = [
        "# Zero leakage at no utility cost (H1)",
        "",
        "Synthetic, scripted workspace; lexical search only; k = {}. {} trials"
        " (seeds 0 to {}),".format(K, trials, trials - 1),
        "{} leakage, {} owner, {} utility and {} over-blocking items. See the".format(
            leakage["items"], owner["items"], utility["items"], over["items"]
        ),
        "docstring of `experiments/audience_utility.py` for the design and decision rule.",
        "",
        "| Arm | Leaks | Owner hit@k | Utility mean RR | Utility hit@k | Mean results shown |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for arm in ARMS:
        row = utility["by_arm"][arm]
        lines.append(
            "| {} | {} ({}) | {} ({}) | {:.4f} | {:.1%} | {:.2f} |".format(
                ARM_LABELS[arm],
                leakage["by_arm"][arm]["leaks"],
                _percent(leakage["by_arm"][arm]["leaks"], leakage["items"]),
                owner["by_arm"][arm]["hits"],
                _percent(owner["by_arm"][arm]["hits"], owner["items"]),
                row["mean_rr"],
                row["hit_at_k"],
                row["mean_shown"],
            )
        )
    lines += [
        "",
        "Utility differences: per-trial mean RR of built minus the other arm, with a",
        "95% percentile bootstrap CI over trials ({:,} resamples).".format(
            BOOTSTRAP_SAMPLES
        ),
        "",
        "| Comparison | Mean D | 95% CI | Trials higher / equal / lower | Reading |",
        "| --- | --- | --- | --- | --- |",
    ]
    for index, (name, arm) in enumerate(COMPARISONS):
        difference = utility["differences"][name]
        lines.append(
            "| built minus {} ({}) | {:+.4f} | {:+.4f} to {:+.4f} | {} / {} / {} | {} |".format(
                arm,
                "rule 4" if index == 0 else "descriptive",
                difference["mean"],
                difference["ci95"][0],
                difference["ci95"][1],
                difference["higher"],
                difference["equal"],
                difference["lower"],
                utility_reading(difference["ci95"]),
            )
        )
    lines += [
        "",
        "Over-blocking (each `general` canary asked by each member, built arm,"
        " `limit={}`):".format(BIG),
        "returned in {} of {} items, within the first k in {} ({}).".format(
            over["returned"],
            over["items"],
            over["hit_at_k"],
            _percent(over["hit_at_k"], over["items"]),
        ),
        "",
        "Sanity: the largest store held {} memories (BIG = {} covers every store: {});".format(
            sanity["most_memories"], BIG, sanity["big_covers_every_store"]
        ),
        "write timestamps rose strictly in write order in {} of {} trials.".format(
            sanity["timestamps_increase"], trials
        ),
        "",
        "Decision:",
        "",
        "- Rule 1, pooled leaks in at least {:.0%} of leakage items: {} ({})".format(
            POOLED_LEAK_SHARE,
            decision["rule_1_pooled_leaks"],
            _percent(leakage["by_arm"]["pooled"]["leaks"], leakage["items"]),
        ),
        "- Rule 1, owner hit@k in the built arm at least {:.0%}: {} ({}{})".format(
            OWNER_HIT_SHARE,
            decision["rule_1_owner_finds_canary"],
            _percent(owner["by_arm"]["built"]["hits"], owner["items"]),
            ""
            if owner["built_first_miss_seed"] is None
            else ", first seed with a miss {}".format(owner["built_first_miss_seed"]),
        ),
        "- Rule 2, every over-blocking item returned by the built arm: {} ({} missing{})".format(
            decision["rule_2_no_over_blocking"],
            over["missing"],
            ""
            if over["first_seed"] is None
            else ", first failing seed {}".format(over["first_seed"]),
        ),
        "- Rule 3, zero leakage in after-k, after-all and built: {}{}".format(
            decision["rule_3_zero_leakage"],
            "".join(
                "; {} leaked in {} trials (first failing seed {})".format(
                    arm,
                    leakage["by_arm"][arm]["trials_with_leak"],
                    leakage["by_arm"][arm]["first_seed"],
                )
                for arm in FILTERED_ARMS
                if leakage["by_arm"][arm]["leaks"]
            ),
        ),
        "- Rule 4, utility of built against after-all: {}".format(
            decision["rule_4_utility"]
        ),
        "- **Verdict: {}**".format(decision["verdict"]),
        "",
        "Limits: the data were written alongside the code, so this shows that the",
        "mechanism works, not how often it matters in real use. Gold memories are the",
        "only memories that contain both query words, so a ranker that keeps every",
        "visible memory puts gold first in almost every item; rule 4 checks that the",
        "built path loses or misorders no visible memory, and has little power to show",
        "a subtler ranking cost. Only lexical search was tested (no embedder, no links,",
        "no keys); the link paths are tested in `experiments/audience_link_paths.py`.",
        "",
    ]
    return "\n".join(lines)


def report_for(trials: list) -> dict:
    summary = summarise(trials)
    return {
        "trials": len(trials),
        "settings": {
            "members": list(MEMBERS),
            "channels": list(CHANNELS),
            "private_channel_sizes": list(PRIVATE_SIZES),
            "subjects": len(SUBJECTS),
            "attributes": list(ATTRIBUTES),
            "values": len(VALUES),
            "filler_words": len(FILLER),
            "max_filler_words": MAX_FILLER_WORDS,
            "facts_per_channel": FACTS_PER_CHANNEL,
            "canaries_per_channel": CANARIES_PER_CHANNEL,
            "k": K,
            "big": BIG,
            "utility_pairs_per_viewer": UTILITY_PAIRS_PER_VIEWER,
            "bootstrap_samples": BOOTSTRAP_SAMPLES,
            "bootstrap_seed": BOOTSTRAP_SEED,
            "utility_margin": UTILITY_MARGIN,
            "pooled_leak_share": POOLED_LEAK_SHARE,
            "owner_hit_share": OWNER_HIT_SHARE,
        },
        "summary": summary,
        "decision": decide(summary, len(trials)),
    }


# Harder workload (``--hard``), designed 2026-11-27; see the docstring.
H_PRIVATE_SIZES = (1, 2, 3, 4, 5)
H_SUBJECTS = tuple("sub{:02d}".format(index) for index in range(12))
H_ATTRIBUTES = ATTRIBUTES + ("scope", "quota", "region", "sponsor")
H_TEMPLATE_WORDS = (
    "the", "of", "is", "noted", "and", "in", "passing", "report", "sync", "notes", "unaffected"
)
H_CHANNEL_WEIGHTS = (2, 1, 1, 1)  # general, p1, p2, p3
H_FOCUS_PAIRS = 8
H_ANSWERS = (3, 6)
H_MENTIONS = (2, 4)
H_ATTRIBUTE_HEAVY = 3
H_SUBJECT_HEAVY = 3
H_DECOYS = 2
H_REPEATS = (1, 3)
H_LONG_FILLER = 20
H_SHORT_FILLER = 2
H_BACKGROUND = 40
H_BACKGROUND_FILLER = 12
H_CANARIES_PER_CHANNEL = 3
H_GROUP_SIZES = (2, 2, 2, 3, 3, 3)
H_RECALL_K = 3
H_METRICS = ("ndcg", "rr", "recall")
H_METRIC_LABELS = {"ndcg": "nDCG@10", "rr": "RR", "recall": "recall@3"}
H_FAULTS = ("fault-drop-term", "fault-swap-top")
H_ARMS = ARMS + H_FAULTS
H_ARM_LABELS = dict(
    ARM_LABELS,
    **{
        "fault-drop-term": "fault: built without its rarest query word",
        "fault-swap-top": "fault: built with its first two swapped",
    }
)
# (key, arm, arm subtracted, role); rule 7 and rule 4 read the first four.
H_COMPARISONS = (
    ("built_minus_after_all", "built", "after-all", "rule 7"),
    ("drop_term_minus_after_all", "fault-drop-term", "after-all", "rule 4"),
    ("swap_top_minus_after_all", "fault-swap-top", "after-all", "rule 4"),
    ("built_minus_after_k", "built", "after-k", "descriptive"),
    ("built_minus_pooled", "built", "pooled", "descriptive"),
)
H_CEILING_TRIAL_SHARE = 0.95
H_CEILING_ITEM_SHARE = 0.2
H_REFERENCE_BELOW_ONE_SHARE = 0.2
H_DETERMINISM_SEEDS = 3
H_ITEM_TYPES = ("utility", "ceiling", "leakage", "owner", "over_blocking")
WORD = re.compile(r"\w+", re.UNICODE)


def _filler_words(rng: random.Random, most: int) -> list:
    return [rng.choice(FILLER) for _ in range(rng.randint(0, most))]


def hard_build_workspace(seed: int) -> dict:
    """Memberships, focus pairs and memories of one hard trial, in write order."""
    rng = random.Random("{}-hard-workspace".format(seed))
    members = {GENERAL: list(MEMBERS)}
    for channel in PRIVATE_CHANNELS:
        members[channel] = sorted(rng.sample(MEMBERS, rng.choice(H_PRIVATE_SIZES)))
    focus = rng.sample([(s, a) for s in H_SUBJECTS for a in H_ATTRIBUTES], H_FOCUS_PAIRS)
    memories = []

    def add(label, subject, attribute, form, value, words, channel=None):
        if channel is None:
            channel = rng.choices(CHANNELS, weights=H_CHANNEL_WEIGHTS)[0]
        memories.append(
            {
                "label": label,
                "channel": channel,
                "subject": subject,
                "attribute": attribute,
                "form": form,
                "value": value,
                "canary": form == "canary",
                "speaker": rng.choice(members[channel]),
                "content": " ".join(words),
            }
        )

    def other(choices, not_this):
        return rng.choice([choice for choice in choices if choice != not_this])

    for number, (s, a) in enumerate(focus):
        prefix = "f{}".format(number)
        for index in range(rng.randint(*H_ANSWERS)):
            value = rng.choice(VALUES)
            sentence = "The {} of {} is {}.".format(a, s, value)
            add("{}/answer{}".format(prefix, index), s, a, "answer", value,
                [sentence] + _filler_words(rng, H_LONG_FILLER))
        for index in range(rng.randint(*H_MENTIONS)):
            sentence = "Noted {} and {} in passing.".format(s, a)
            add("{}/mention{}".format(prefix, index), s, a, "mention", None,
                [sentence] + _filler_words(rng, H_LONG_FILLER))
        for index in range(H_ATTRIBUTE_HEAVY):
            s2, value = other(H_SUBJECTS, s), rng.choice(VALUES)
            lead = [a] * rng.randint(*H_REPEATS)
            sentence = "report: The {} of {} is {}.".format(a, s2, value)
            add("{}/attribute{}".format(prefix, index), s2, a, "answer", value,
                lead + [sentence] + _filler_words(rng, H_SHORT_FILLER))
        for index in range(H_SUBJECT_HEAVY):
            a2, value = other(H_ATTRIBUTES, a), rng.choice(VALUES)
            lead = [s] * rng.randint(*H_REPEATS)
            sentence = "sync notes: The {} of {} is {}.".format(a2, s, value)
            add("{}/subject{}".format(prefix, index), s, a2, "answer", value,
                lead + [sentence] + _filler_words(rng, H_SHORT_FILLER))
        for index in range(H_DECOYS):
            s2, value = other(H_SUBJECTS, s), rng.choice(VALUES)
            sentence = "The {} of {} is {}; {} unaffected.".format(a, s2, value, s)
            add("{}/decoy{}".format(prefix, index), s2, a, "answer", value,
                [sentence] + _filler_words(rng, H_SHORT_FILLER))
    for index in range(H_BACKGROUND):
        s, a, value = rng.choice(H_SUBJECTS), rng.choice(H_ATTRIBUTES), rng.choice(VALUES)
        add("background{:02d}".format(index), s, a, "answer", value,
            ["The {} of {} is {}.".format(a, s, value)]
            + _filler_words(rng, H_BACKGROUND_FILLER))
    canary_number = 0
    for channel in CHANNELS:
        for index in range(H_CANARIES_PER_CHANNEL):
            s, a = rng.choice(H_SUBJECTS), rng.choice(H_ATTRIBUTES)
            value = "canary{}h{}".format(seed, canary_number)
            canary_number += 1
            add("{}/canary{}".format(channel, index), s, a, "canary", value,
                ["The {} of {} is {}.".format(a, s, value)]
                + _filler_words(rng, H_BACKGROUND_FILLER), channel=channel)
    rng.shuffle(memories)
    return {
        "seed": seed,
        "members": members,
        "focus": [list(pair) for pair in focus],
        "memories": memories,
    }


def grade(memory: dict, subject: str, attribute: str) -> int:
    """The memory's grade for the query of (subject, attribute)."""
    if (memory["subject"], memory["attribute"]) != (subject, attribute):
        return 0
    return 1 if memory["form"] == "mention" else 2


def audience_sees(workspace: dict, audience, channel: str) -> bool:
    """Every audience member belongs to the channel, from the experiment's record."""
    return set(audience) <= set(workspace["members"][channel])


def hard_questions(workspace: dict) -> list:
    """Every question of a hard trial, before any store exists."""
    rng = random.Random("{}-hard-questions".format(workspace["seed"]))
    audiences = [[member] for member in MEMBERS] + [
        sorted(rng.sample(MEMBERS, size)) for size in H_GROUP_SIZES
    ]
    memories = workspace["memories"]
    asked = []
    for audience in audiences:
        visible = [m for m in memories if audience_sees(workspace, audience, m["channel"])]
        for subject, attribute in workspace["focus"]:
            gold = {
                memory["label"]: grade(memory, subject, attribute)
                for memory in sorted(visible, key=lambda memory: memory["label"])
                if grade(memory, subject, attribute)
            }
            if 2 in gold.values():
                asked.append(
                    {
                        "type": "utility",
                        "audience": audience,
                        "query": "{} {}".format(attribute, subject),
                        "gold": gold,
                    }
                )
    for subject, attribute in workspace["focus"]:
        asked.append(
            {
                "type": "ceiling",
                "audience": None,
                "query": "{} {}".format(attribute, subject),
                "gold": {
                    memory["label"]: grade(memory, subject, attribute)
                    for memory in sorted(memories, key=lambda memory: memory["label"])
                    if grade(memory, subject, attribute)
                },
            }
        )
    canaries = sorted((m for m in memories if m["canary"]), key=lambda m: m["label"])
    private = [canary for canary in canaries if canary["channel"] != GENERAL]

    def canary_query(canary):
        return "{} {} {}".format(canary["attribute"], canary["subject"], canary["value"])

    for audience in audiences:
        for canary in private:
            if not audience_sees(workspace, audience, canary["channel"]):
                asked.append(
                    {
                        "type": "leakage",
                        "audience": audience,
                        "query": canary_query(canary),
                        "canary": canary["label"],
                    }
                )
    for canary in private:
        asked.append(
            {
                "type": "owner",
                "audience": [canary["speaker"]],
                "query": canary_query(canary),
                "canary": canary["label"],
            }
        )
    for canary in canaries:
        if canary["channel"] == GENERAL:
            for audience in audiences:
                asked.append(
                    {
                        "type": "over_blocking",
                        "audience": audience,
                        "query": canary_query(canary),
                        "canary": canary["label"],
                    }
                )
    return asked


def drop_rarest_word(query: str, frequency: dict) -> str:
    """The query without the word the fewest memories contain (ties: first by sort)."""
    words = query.split()
    rarest = min(words, key=lambda word: (frequency.get(word, 0), word))
    return " ".join(word for word in words if word != rarest)


def hard_answer(store: MemoryStore, labels: dict, workspace: dict, asked: list, fault=None) -> list:
    """Ask every hard question in its arms; return the questions with what was shown."""
    channel_of = {memory["label"]: memory["channel"] for memory in workspace["memories"]}
    frequency = {}
    for memory in workspace["memories"]:
        for word in set(WORD.findall(memory["content"].lower())):
            frequency[word] = frequency.get(word, 0) + 1
    calls = {}

    def read(query: str, limit: int, audience=None) -> list:
        key = (query, limit, audience)
        if key not in calls:
            calls[key] = [
                labels.get(result.memory.id, "?" + result.memory.id)
                for result in store.search(
                    query,
                    limit=limit,
                    record_access=False,
                    viewers=None if audience is None else list(audience),
                )
            ]
        return calls[key]

    def visible(audience, label: str) -> bool:
        channel = channel_of.get(label)
        return channel is not None and audience_sees(workspace, audience, channel)

    answered = []
    for item in asked:
        audience = None if item["audience"] is None else tuple(item["audience"])
        query = item["query"]
        if item["type"] == "ceiling":
            shown = {"pooled": read(query, BIG)[:K]}
        elif item["type"] == "over_blocking":
            shown = {"built": list(read(query, BIG, audience))}
        else:
            shown = shown_by_arm(read, visible, audience, query)
            if item["type"] == "utility":
                built = shown["built"]
                shown["fault-drop-term"] = list(
                    read(drop_rarest_word(query, frequency), K, audience)
                )
                shown["fault-swap-top"] = built[1:2] + built[:1] + built[2:]
                if fault is not None:
                    shown["built"] = list(shown[fault])
        answered.append(dict(item, shown=shown))
    return answered


def ndcg_at_k(shown: list, gold: dict) -> float:
    def dcg(grades):
        return sum((2 ** g - 1) / math.log2(rank + 1) for rank, g in enumerate(grades, start=1))

    ideal = dcg(sorted(gold.values(), reverse=True)[:K])
    return dcg([gold.get(label, 0) for label in shown[:K]]) / ideal if ideal else 0.0


def graded_reciprocal_rank(shown: list, gold: dict) -> float:
    for rank, label in enumerate(shown[:K], start=1):
        if gold.get(label, 0) == 2:
            return 1.0 / rank
    return 0.0


def recall_at(shown: list, gold: dict, depth: int = H_RECALL_K) -> float:
    relevant = [label for label, g in gold.items() if g >= 1]
    top = set(shown[:depth])
    return sum(label in top for label in relevant) / len(relevant) if relevant else 0.0


H_METRIC_FUNCTIONS = {"ndcg": ndcg_at_k, "rr": graded_reciprocal_rank, "recall": recall_at}


def hard_score_items(items: list) -> dict:
    """Per-trial counts and means from the answered hard questions."""
    by_type = {name: [item for item in items if item["type"] == name] for name in H_ITEM_TYPES}
    utility = by_type["utility"]
    values = {
        arm: {
            metric: [H_METRIC_FUNCTIONS[metric](item["shown"][arm], item["gold"]) for item in utility]
            for metric in H_METRICS
        }
        for arm in H_ARMS
    }
    count = len(utility)

    def mean(numbers):
        return sum(numbers) / len(numbers) if numbers else 0.0

    scores = {
        "utility": {
            "items": count,
            "metrics": {arm: {m: mean(values[arm][m]) for m in H_METRICS} for arm in H_ARMS},
            "hit": {arm: mean([rr > 0 for rr in values[arm]["rr"]]) for arm in H_ARMS},
            "shown": {arm: mean([len(item["shown"][arm]) for item in utility]) for arm in H_ARMS},
            "items_compared": {
                key: {
                    metric: {
                        "higher": sum(x - y > ZERO for x, y in zip(values[arm][metric], values[other][metric])),
                        "equal": sum(abs(x - y) <= ZERO for x, y in zip(values[arm][metric], values[other][metric])),
                        "lower": sum(x - y < -ZERO for x, y in zip(values[arm][metric], values[other][metric])),
                    }
                    for metric in H_METRICS
                }
                for key, arm, other, _ in H_COMPARISONS
            },
            "after_all_ndcg_below_one": sum(v < 1 - ZERO for v in values["after-all"]["ndcg"]),
            "same_list_as_after_all": sum(
                item["shown"]["built"] == item["shown"]["after-all"] for item in utility
            ),
        }
    }
    ceiling = [graded_reciprocal_rank(item["shown"]["pooled"], item["gold"]) for item in by_type["ceiling"]]
    scores["ceiling"] = {
        "items": len(ceiling),
        "mean_rr": mean(ceiling),
        "below_one": sum(rr < 1 - ZERO for rr in ceiling),
    }
    for name, field in (("leakage", "leaks"), ("owner", "hits")):
        scores[name] = {
            "items": len(by_type[name]),
            field: {
                arm: sum(item["canary"] in item["shown"][arm][:K] for item in by_type[name])
                for arm in ARMS
            },
        }
    over = by_type["over_blocking"]
    scores["over_blocking"] = {
        "items": len(over),
        "returned": sum(item["canary"] in item["shown"]["built"] for item in over),
        "hit_at_k": sum(item["canary"] in item["shown"]["built"][:K] for item in over),
    }
    return scores


def hard_run_trial(seed: int, fault=None) -> dict:
    workspace = hard_build_workspace(seed)
    asked = hard_questions(workspace)
    with MemoryStore(":memory:") as store:
        labels, stamps = populate(store, workspace)
        items = hard_answer(store, labels, workspace, asked, fault)
    return {
        "seed": seed,
        "members": {channel: workspace["members"][channel] for channel in PRIVATE_CHANNELS},
        "focus": workspace["focus"],
        "memories": len(labels),
        "timestamps_increase": all(earlier < later for earlier, later in zip(stamps, stamps[1:])),
        "items": items,
        "scores": hard_score_items(items),
    }


def sign_test(higher: int, lower: int) -> float:
    """Exact two-sided sign test p-value, ties dropped."""
    n = higher + lower
    if n == 0:
        return 1.0
    tail = sum(math.comb(n, i) for i in range(min(higher, lower) + 1)) / 2.0 ** n
    return min(1.0, 2 * tail)


def difference_readings(ci95: list) -> dict:
    lower, upper = ci95
    return {
        "reading": utility_reading(ci95),
        "equal_within_margin": lower >= -UTILITY_MARGIN and upper <= UTILITY_MARGIN,
        "difference_detected": lower > ZERO or upper < -ZERO,
    }


def hard_summarise(trials: list, rerun=None) -> dict:
    """Summary of hard trials; ``rerun`` holds the determinism reruns."""
    base = summarise(
        [dict(trial, scores=dict(trial["scores"], utility={
            "items": trial["scores"]["utility"]["items"],
            "rr": {arm: trial["scores"]["utility"]["metrics"][arm]["rr"] for arm in ARMS},
            "hit": trial["scores"]["utility"]["hit"],
            "shown": trial["scores"]["utility"]["shown"],
        })) for trial in trials]
    )
    count = len(trials)
    utility_items = sum(trial["scores"]["utility"]["items"] for trial in trials)
    per_trial = {
        arm: {m: [trial["scores"]["utility"]["metrics"][arm][m] for trial in trials] for m in H_METRICS}
        for arm in H_ARMS
    }
    differences = {}
    for key, arm, other, role in H_COMPARISONS:
        differences[key] = {"arm": arm, "minus": other, "role": role, "metrics": {}}
        for metric in H_METRICS:
            result = bootstrap([x - y for x, y in zip(per_trial[arm][metric], per_trial[other][metric])])
            result.update(difference_readings(result["ci95"]))
            result["sign_test_p"] = sign_test(result["higher"], result["lower"])
            result["items"] = {
                side: sum(t["scores"]["utility"]["items_compared"][key][metric][side] for t in trials)
                for side in ("higher", "equal", "lower")
            }
            differences[key]["metrics"][metric] = result
    utility = {
        "items": utility_items,
        "by_arm": {
            arm: dict(
                {m: sum(per_trial[arm][m]) / count for m in H_METRICS},
                hit_at_k=sum(t["scores"]["utility"]["hit"][arm] for t in trials) / count,
                mean_shown=sum(t["scores"]["utility"]["shown"][arm] for t in trials) / count,
            )
            for arm in H_ARMS
        },
        "differences": differences,
        "same_list_as_after_all": sum(t["scores"]["utility"]["same_list_as_after_all"] for t in trials),
        "after_all_ndcg_below_one": sum(t["scores"]["utility"]["after_all_ndcg_below_one"] for t in trials),
    }
    ceiling_items = sum(t["scores"]["ceiling"]["items"] for t in trials)
    ceiling = {
        "items": ceiling_items,
        "mean_rr": sum(t["scores"]["ceiling"]["mean_rr"] for t in trials) / count,
        "items_below_one": sum(t["scores"]["ceiling"]["below_one"] for t in trials),
        "trials_below_one": sum(t["scores"]["ceiling"]["mean_rr"] < 1 - ZERO for t in trials),
    }
    rerun = rerun or []
    return dict(
        base,
        utility=utility,
        ceiling=ceiling,
        determinism={
            "seeds": [trial["seed"] for trial in rerun],
            "identical": bool(rerun) and rerun == trials[: len(rerun)],
        },
    )


def hard_decide(summary: dict) -> dict:
    """Apply the hard decision rule (rules 1 to 7 of the hard section) to a summary."""
    trials = summary["trials"]
    leakage = summary["leakage"]
    pooled_share = _share(leakage["by_arm"]["pooled"]["leaks"], leakage["items"])
    pooled_leaks = pooled_share is not None and pooled_share >= POOLED_LEAK_SHARE
    owner_share = _share(summary["owner"]["by_arm"]["built"]["hits"], summary["owner"]["items"])
    owner_finds = owner_share is not None and owner_share >= OWNER_HIT_SHARE
    over = summary["over_blocking"]
    no_over_blocking = over["items"] > 0 and over["missing"] == 0
    ceiling = summary["ceiling"]
    utility = summary["utility"]
    ceiling_checks = {
        "trials_below_one": (_share(ceiling["trials_below_one"], trials) or 0) >= H_CEILING_TRIAL_SHARE,
        "items_below_one": (_share(ceiling["items_below_one"], ceiling["items"]) or 0)
        >= H_CEILING_ITEM_SHARE,
        "after_all_below_one": (_share(utility["after_all_ndcg_below_one"], utility["items"]) or 0)
        >= H_REFERENCE_BELOW_ONE_SHARE,
    }
    below_ceiling = all(ceiling_checks.values())
    differences = utility["differences"]
    faults_detected = {
        key: differences[key]["metrics"]["ndcg"]["reading"] == "utility cost"
        for key, _, _, role in H_COMPARISONS
        if role == "rule 4"
    }
    deterministic = summary["determinism"]["identical"]
    clean = {arm: leakage["by_arm"][arm]["leaks"] == 0 for arm in FILTERED_ARMS}
    zero_leakage = all(clean.values())
    readings = {m: differences["built_minus_after_all"]["metrics"][m]["reading"] for m in H_METRICS}

    reasons = []
    if not zero_leakage:
        reasons.append(
            "rule 6, leaks in "
            + ", ".join(
                "{} ({} of {} items, first failing seed {})".format(
                    arm, leakage["by_arm"][arm]["leaks"], leakage["items"],
                    leakage["by_arm"][arm]["first_seed"],
                )
                for arm in FILTERED_ARMS
                if not clean[arm]
            )
        )
    for metric in H_METRICS:
        if readings[metric] != "no utility cost":
            result = differences["built_minus_after_all"]["metrics"][metric]
            reasons.append(
                "rule 7, {} on {} (built minus after-all {:+.4f}, 95% CI {:+.4f} to {:+.4f})".format(
                    "utility cost" if readings[metric] == "utility cost" else "utility unclear",
                    H_METRIC_LABELS[metric], result["mean"], result["ci95"][0], result["ci95"][1],
                )
            )
    controls = (
        pooled_leaks and owner_finds and no_over_blocking and below_ceiling
        and all(faults_detected.values()) and deterministic
    )
    if not controls:
        verdict = "inconclusive (a control failed)"
    elif not reasons:
        verdict = "H1 supported"
    else:
        verdict = "H1 not supported: " + "; ".join(reasons)
    return {
        "rule_1_pooled_leaks": pooled_leaks,
        "rule_1_owner_finds_canary": owner_finds,
        "rule_2_no_over_blocking": no_over_blocking,
        "rule_3_below_ceiling": below_ceiling,
        "rule_3_checks": ceiling_checks,
        "rule_4_faults_detected": all(faults_detected.values()),
        "rule_4_by_fault": faults_detected,
        "rule_5_deterministic": deterministic,
        "rule_6_zero_leakage": zero_leakage,
        "rule_6_zero_leakage_by_arm": clean,
        "rule_7_utility": readings,
        "reasons": reasons,
        "verdict": verdict,
    }


def hard_report_for(trials: list, rerun=None, fault=None) -> dict:
    summary = hard_summarise(trials, rerun)
    return {
        "trials": len(trials),
        "mode": "hard",
        "fault": fault,
        "settings": {
            "members": list(MEMBERS),
            "channels": list(CHANNELS),
            "private_channel_sizes": list(H_PRIVATE_SIZES),
            "channel_weights": list(H_CHANNEL_WEIGHTS),
            "subjects": len(H_SUBJECTS),
            "attributes": list(H_ATTRIBUTES),
            "focus_pairs": H_FOCUS_PAIRS,
            "answers": list(H_ANSWERS),
            "mentions": list(H_MENTIONS),
            "attribute_heavy": H_ATTRIBUTE_HEAVY,
            "subject_heavy": H_SUBJECT_HEAVY,
            "decoys": H_DECOYS,
            "repeats": list(H_REPEATS),
            "long_filler": H_LONG_FILLER,
            "short_filler": H_SHORT_FILLER,
            "background": H_BACKGROUND,
            "background_filler": H_BACKGROUND_FILLER,
            "canaries_per_channel": H_CANARIES_PER_CHANNEL,
            "group_sizes": list(H_GROUP_SIZES),
            "k": K,
            "recall_k": H_RECALL_K,
            "big": BIG,
            "bootstrap_samples": BOOTSTRAP_SAMPLES,
            "bootstrap_seed": BOOTSTRAP_SEED,
            "utility_margin": UTILITY_MARGIN,
            "pooled_leak_share": POOLED_LEAK_SHARE,
            "owner_hit_share": OWNER_HIT_SHARE,
            "ceiling_trial_share": H_CEILING_TRIAL_SHARE,
            "ceiling_item_share": H_CEILING_ITEM_SHARE,
            "reference_below_one_share": H_REFERENCE_BELOW_ONE_SHARE,
            "determinism_seeds": H_DETERMINISM_SEEDS,
        },
        "summary": summary,
        "decision": hard_decide(summary),
    }


def hard_run(trials: int, fault=None) -> dict:
    """Run the hard trials and the determinism reruns; return the report."""
    results = [hard_run_trial(seed, fault) for seed in range(trials)]
    rerun = [hard_run_trial(seed, fault) for seed in range(min(H_DETERMINISM_SEEDS, trials))]
    return hard_report_for(results, rerun, fault)


def hard_render(report: dict) -> str:
    trials = report["trials"]
    summary = report["summary"]
    decision = report["decision"]
    leakage, owner, over = summary["leakage"], summary["owner"], summary["over_blocking"]
    utility, ceiling = summary["utility"], summary["ceiling"]
    lines = [
        "# Zero leakage at no utility cost (H1), hard workload",
        "",
        "Synthetic, scripted workspace with distractors that share query words, graded",
        "relevance and audiences of one to three people; lexical search only; k = {}.".format(K),
        "{} trials (seeds 0 to {}){}; {} utility, {} ceiling, {} leakage, {} owner and {}".format(
            trials, trials - 1,
            "" if report["fault"] is None
            else ", with {} in place of the built arm".format(report["fault"]),
            utility["items"], ceiling["items"], leakage["items"], owner["items"], over["items"],
        ),
        "over-blocking items. See the hard section of the docstring of",
        "`experiments/audience_utility.py` for the design and decision rule.",
        "",
        "| Arm | Leaks | Owner hit@k | nDCG@10 | RR | recall@3 | hit@k | Mean shown |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for arm in H_ARMS:
        row = utility["by_arm"][arm]
        if arm in ARMS:
            access = "{} ({}) | {} ({})".format(
                leakage["by_arm"][arm]["leaks"],
                _percent(leakage["by_arm"][arm]["leaks"], leakage["items"]),
                owner["by_arm"][arm]["hits"],
                _percent(owner["by_arm"][arm]["hits"], owner["items"]),
            )
        else:
            access = "n/a | n/a"
        lines.append(
            "| {} | {} | {:.4f} | {:.4f} | {:.4f} | {:.1%} | {:.2f} |".format(
                H_ARM_LABELS[arm], access, row["ndcg"], row["rr"], row["recall"],
                row["hit_at_k"], row["mean_shown"],
            )
        )
    lines += [
        "",
        "Differences: per-trial mean of the arm minus the other arm, 95% percentile",
        "bootstrap CI over trials ({:,} resamples); sign test over trials, two-sided.".format(
            BOOTSTRAP_SAMPLES
        ),
        "",
        "| Comparison | Role | Metric | Mean D | 95% CI | Trials + / = / - | Sign p | Items + / = / - | Reading |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for key, arm, other, role in H_COMPARISONS:
        for metric in H_METRICS:
            result = utility["differences"][key]["metrics"][metric]
            notes = [result["reading"]]
            if result["equal_within_margin"]:
                notes.append("equal within the margin")
            if result["difference_detected"]:
                notes.append("difference detected")
            lines.append(
                "| {} minus {} | {} | {} | {:+.4f} | {:+.4f} to {:+.4f} | {} / {} / {} | {:.3g} | {} / {} / {} | {} |".format(
                    arm, other, role, H_METRIC_LABELS[metric], result["mean"],
                    result["ci95"][0], result["ci95"][1],
                    result["higher"], result["equal"], result["lower"], result["sign_test_p"],
                    result["items"]["higher"], result["items"]["equal"], result["items"]["lower"],
                    "; ".join(notes),
                )
            )
    checks = decision["rule_3_checks"]
    lines += [
        "",
        "Built and after-all showed the same list in {} of {} utility items ({}).".format(
            utility["same_list_as_after_all"], utility["items"],
            _percent(utility["same_list_as_after_all"], utility["items"]),
        ),
        "Ceiling (each focus pair, pooled, no audience, store-wide gold): mean RR {:.4f};".format(
            ceiling["mean_rr"]
        ),
        "RR below 1.0 in {} of {} items ({}); trial mean below 1.0 in {} of {} trials ({}).".format(
            ceiling["items_below_one"], ceiling["items"],
            _percent(ceiling["items_below_one"], ceiling["items"]),
            ceiling["trials_below_one"], trials, _percent(ceiling["trials_below_one"], trials),
        ),
        "After-all nDCG@10 below 1.0 in {} of {} utility items ({}).".format(
            utility["after_all_ndcg_below_one"], utility["items"],
            _percent(utility["after_all_ndcg_below_one"], utility["items"]),
        ),
        "Over-blocking: returned in {} of {} items, within the first k in {} ({}).".format(
            over["returned"], over["items"], over["hit_at_k"], _percent(over["hit_at_k"], over["items"])
        ),
        "Determinism: seeds {} rerun from scratch, identical: {}.".format(
            summary["determinism"]["seeds"], summary["determinism"]["identical"]
        ),
        "Sanity: the largest store held {} memories (BIG = {} covers every store: {});".format(
            summary["sanity"]["most_memories"], BIG, summary["sanity"]["big_covers_every_store"]
        ),
        "write timestamps rose strictly in write order in {} of {} trials.".format(
            summary["sanity"]["timestamps_increase"], trials
        ),
        "",
        "Decision:",
        "",
        "- Rule 1, pooled leaks in at least {:.0%} of leakage items: {} ({})".format(
            POOLED_LEAK_SHARE, decision["rule_1_pooled_leaks"],
            _percent(leakage["by_arm"]["pooled"]["leaks"], leakage["items"]),
        ),
        "- Rule 1, owner hit@k in the built arm at least {:.0%}: {} ({})".format(
            OWNER_HIT_SHARE, decision["rule_1_owner_finds_canary"],
            _percent(owner["by_arm"]["built"]["hits"], owner["items"]),
        ),
        "- Rule 2, every over-blocking item returned: {} ({} missing)".format(
            decision["rule_2_no_over_blocking"], over["missing"]
        ),
        "- Rule 3, below the ceiling: {} (trials {}, ceiling items {}, after-all items {})".format(
            decision["rule_3_below_ceiling"], checks["trials_below_one"],
            checks["items_below_one"], checks["after_all_below_one"],
        ),
        "- Rule 4, both planted faults read as a utility cost on nDCG@10: {} ({})".format(
            decision["rule_4_faults_detected"],
            ", ".join("{} {}".format(k, v) for k, v in decision["rule_4_by_fault"].items()),
        ),
        "- Rule 5, deterministic: {}".format(decision["rule_5_deterministic"]),
        "- Rule 6, zero leakage in after-k, after-all and built: {}".format(
            decision["rule_6_zero_leakage"]
        ),
        "- Rule 7, built against after-all: {}".format(
            ", ".join("{} {}".format(H_METRIC_LABELS[m], decision["rule_7_utility"][m]) for m in H_METRICS)
        ),
        "- **Verdict: {}**".format(decision["verdict"]),
        "",
        "Limits: the data were written alongside the code. Grades come from the",
        "generator, not from people. Only lexical search was tested (no embedder,",
        "no links, no keys), and the audiences and channels are small.",
        "",
    ]
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--trials", type=int, default=DEFAULT_TRIALS)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--hard", action="store_true", help="the harder workload (2026-11-27)")
    parser.add_argument("--fault", choices=H_FAULTS, help="with --hard, a planted fault in the built arm")
    arguments = parser.parse_args(argv)
    if arguments.trials < 1:
        parser.error("--trials must be positive")
    if arguments.fault and not arguments.hard:
        parser.error("--fault needs --hard")

    if arguments.hard:
        name = "audience_utility_hard" + ("" if arguments.fault is None else "_" + arguments.fault)
        output = arguments.output or ROOT / "experiments" / "results" / name
        report = hard_run(arguments.trials, arguments.fault)
        text = hard_render(report)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.with_suffix(".json").write_text(json.dumps(report, indent=2) + "\n")
        output.with_suffix(".md").write_text(text)
        print(text)
        return 0

    arguments.output = arguments.output or ROOT / "experiments" / "results" / "audience_utility"
    report = report_for([run_trial(seed) for seed in range(arguments.trials)])
    text = render(report)
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.with_suffix(".json").write_text(json.dumps(report, indent=2) + "\n")
    arguments.output.with_suffix(".md").write_text(text)
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
