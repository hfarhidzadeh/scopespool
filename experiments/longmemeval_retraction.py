"""Retraction on real conversation text: does it erase, and does it act like never writing?

Question (follows H5 of section 9 of docs/multi_user_memory_review.md, which was
tested on invented tokens). When a speaker retracts a message whose text is real
conversation, (a) is every stored copy of its words gone from the database,
(b) does a store that retracted behave, for readers, like a store that never
received the message, and (c) does the rest still work (other messages, rebuild
of derived memories from the remaining sources, an older backup with a key file)?
Real text differs from the earlier canaries: it repeats phrases, has no unique
token, and is long, so "its words" must be defined without a planted marker.

Data. LongMemEval_S (cleaned), the same file and parser as the shared-workspace
experiment, no LLM. A trial is seed s: it draws one question history and
samples up to 100 of its user turns, kept in their original order. The channel
``history`` has two members, user00 and user01; the turns of each session are
said by one of them (sessions alternate by order of appearance). Each turn is a
message. Derived memories are built as an extractive summary would be: within a
session, consecutive sampled turns are paired with probability 0.5; each memory
lists its 1 or 2 source messages and its text is the sources' text joined by a
space, so every message is the source of exactly one memory. In odd seeds the
consecutive memories of a session are linked ``related_to`` (the "linked"
trials). In seeds with s mod 4 = 3 the store has an embedder (the "hybrid"
trials; ``NGramHashEmbedder``) and every query is run once before the
retraction so that vectors exist.

Distinctive words. A message's text is lower-cased and split into word tokens
(\\w+); its shingles are its 6-token windows. A shingle is *distinctive* to a
message if no other sampled message contains it. A message is retractable if it
has at least 3 distinctive shingles. A retracted message's evidence is its
distinctive shingles: finding one in the stored data means a copy of that
message's words remains. 1 to 3 retractable messages are retracted, each by its
speaker. If a draw has none, the next question is drawn (deterministically).

Scan. Every value of every column of every table, read through SQLite, with
bytes decoded as Latin-1; each value is normalised like the text and the values
are joined with a separator so no shingle spans two values.

Panel of queries per trial, each a read of the audience {user00, user01} with
limit 10 and ``record_access=False``: the first 25 words of each retracted
message; the question's text; the first 25 words of 6 retained messages (3
sources of memories that lose a source, 3 others).

Reference. A store built from the same data in which the retracted messages
were never posted: each memory whose sources are all retracted is absent, and
each other memory has the join of its remaining sources as text. Its memories
are written in the same order, and the store clock is a monotone counter, so
ties break the same way. Links between memories that both exist are kept.

Checks, per trial.
- Determinism (negative control): the trial run twice gives the same result.
- Probe (positive control): before the retraction the scan finds every
  distinctive shingle of every retracted message, and a byte copy of the plain
  database file holds the first 40 characters of each retracted message.
- Specificity: after the retraction, every retained message reads exactly as
  written and every memory with no retracted source has its original text.
- Erasure: after the retraction (before any rebuild) no distinctive shingle of
  a retracted message occurs in any stored value; in hybrid trials no
  embedding is kept for a memory that lost a source.
- Reads: after the retraction, and again after the rebuild, no result of any
  panel query, no message and no listed memory read for the audience holds a
  distinctive shingle of a retracted message; and, in every trial (linked or
  not), after the rebuild no panel query's result has a different ranking from
  the reference's (the same memories in the same order; scores may differ
  within the tolerance 1e-9 or not at all, and are reported). A read that
  returns a different memory list from the reference counts as different.
- Rebuild: ``rebuild_stale`` with the extractive consolidator rebuilds every
  queued memory that has a remaining source, from exactly those sources (its
  text is the join of their text, and it lists exactly them); leaves in the
  queue exactly the memories with no remaining source; and the scan afterwards
  still finds no distinctive shingle.
- Backup: the trial is built again with a key file. A byte copy of the main
  file taken before the retraction holds no retracted text at all (the first
  40 characters of no retracted message), and after the retraction, opening the
  copy with the key file recovers no distinctive shingle from any message or
  memory, while every retained message still reads correctly from it.

Reported, not part of the verdict: how often a message was retractable (the
rest repeat their words elsewhere); how often reads equal the reference
(identical, or the same ranking with different scores or links), in linked and
unlinked trials separately; trials whose raw file still holds the first 40 characters of
a retracted message (only prefixes that no other message shares count); memories derived from retracted messages; and the
undeclared-copy probe: copies of a retracted message's text written as memories
that do not list it as a source are not found by the store, and this counts how
many survive (a documented limit, expected to be all of them).

Decision rule, fixed before running:
  1. Determinism holds in every trial.
  2. The probe holds in every trial.
  3. Specificity holds in every trial.
  4. Erasure holds in every trial.
  5. Reads hold in every trial.
  6. Rebuild holds in every trial.
  7. Backup holds in every trial.
Verdict: "inconclusive (control <n> failed)" if rule 1 or 2 fails; otherwise
"retraction erases on real text" if rules 3 to 7 hold; otherwise "retraction
does not erase (rules <list> failed, first failing seed <s>)". A pass does not
cover text a caller copies into a memory without listing the message.

Validation (positive controls against the store), fixed before running; each
fault is put into the store one at a time and the pattern must appear in at
least 95% of the trials named:
  keep-text (retraction keeps the derived text): rule 4 fails in every trial.
  keep-pads (retraction leaves the pads of the keyed store): rule 7 fails in
    every trial.
  leaky-rebuild (the consolidator also writes the first 15 words of a retracted
    message): rule 6 fails in every trial where some memory can be rebuilt.
  no-rebuild (rebuild_stale is never called): rule 5 fails in every trial
    where some memory can be rebuilt, because the reference holds those
    memories.
The expected pattern of every other rule is not part of the criterion.

Design-time finding (before any recorded run): the first smoke run labelled
the endpoints of links that were outside a read's top 10 by memory id, which
differs between two stores, so every linked read looked "different" in its links.
That was the harness, not the store; endpoints are now labelled by their text.

Second design-time finding (run 1, before the store changed): a memory rebuilt
after a retraction did not inherit the links of the stale memory it replaces, so
in linked trials it lost the graph bonus and ranked differently from the same
memory in a store that never got the message, although its raw lexical and vector
scores were identical (163 of 900 linked queries). Run 1 kept linked reads out
of the verdict for that reason.

Fifth finding (run 2, found when the researcher's carry-over was reviewed): the
first carry-over copied a link only if the other end was live at that moment.
When both ends of a link lose a source, each is stale while the other is
rebuilt, so the link between the two rebuilt memories was lost (4 of 900 linked
queries differed in scores or links in run 2, probably for this reason: they
vanished after the fix but were not traced one by one; a unit test reproduces
the case). The store
now points a link at the live counterpart of a stale end, that is the memory that
rebuilt it, and does the carrying inside the transaction that writes the rebuild.

Runs. Run 1 (committed in c7a7a94; reports in
``experiments/results/longmemeval_retraction_run1_superseded/``): linked reads
outside the verdict; 163 of 900 linked queries differed from the reference.
Run 2 (the researcher's first carry-over; its reports were overwritten and only
its figures survive: linked reads identical 896, same ranking 4, different 0).
Run 3 (this one): the store carries links to live counterparts; linked reads
are in the verdict (rule 5) and the fault criteria cover every trial. The data,
scan and other rules are those of run 1, and all fault validations were rerun.

Third design-time finding (the first full run, discarded): the scan matched a
shingle as a plain substring, so the retracted window "it in the form of a" was
found inside another message's "it in the form of an". Four trials failed rules
4 to 7 for that reason alone. Shingles are now matched on whole tokens, and all
fault validations and the full run were repeated.

Fourth design-time finding (the second full run, also discarded): the raw-file
count used the first 40 characters of each retracted message even when another
message begins the same way, and exactly the 5 trials where that happens were
the 5 reported. The descriptive count now uses only prefixes no other message
shares. No rule changed.

Default: 200 trials (seeds 0 to 199).

Run from the project root:

    python3 -I experiments/longmemeval_retraction.py --jobs 3
    python3 -I experiments/longmemeval_retraction.py --fault keep-text --trials 40 \\
        --output experiments/results/longmemeval_retraction_fault_keep_text
"""

from __future__ import annotations

import argparse
import contextlib
import importlib.util
import json
import multiprocessing
import random
import re
import shutil
import sys
import tempfile
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from dynmemory import MemoryStore, MemoryType, NGramHashEmbedder  # noqa: E402
from dynmemory.consolidation import ExtractiveConsolidator  # noqa: E402
from dynmemory.store import SCHEMA_VERSION  # noqa: E402


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "experiments" / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


stageb = _load("stageb_for_retraction", "longmemeval_shared_workspace.py")
canary = _load("canary_for_retraction", "audience_retraction_canary.py")

CHANNEL = "history"
MEMBERS = ("user00", "user01")
TURNS = 100
SHINGLE = 6
MIN_DISTINCT = 3
QUERY_WORDS = 25
RETRACTIONS = (1, 3)
PAIR_SHARE = 0.5
RAW_PREFIX = 40
LEAK_WORDS = 15
BIG = 100000
DEPTH = 10
DEFAULT_TRIALS = 200
TOKEN = re.compile(r"\w+")
CHECKS = ("determinism", "probe", "specificity", "erasure", "reads", "rebuild", "backup")
RULES = {number: name for number, name in enumerate(CHECKS, start=1)}
CONTROL_RULES = (1, 2)
BUILT_RULES = (3, 4, 5, 6, 7)
FAULTS = ("keep-text", "keep-pads", "leaky-rebuild", "no-rebuild")
FAULT_RULE = {"keep-text": 4, "keep-pads": 7, "leaky-rebuild": 6, "no-rebuild": 5}
FAULT_NEEDS_REBUILD = {"leaky-rebuild", "no-rebuild"}
FAULT_SHARE = 0.95
PARSED = {}
ELIGIBLE = []


# --- text ---------------------------------------------------------------------------


def tokens(text: str) -> list:
    return TOKEN.findall(text.lower())


def shingles(text: str) -> set:
    words = tokens(text)
    return {" ".join(words[i:i + SHINGLE]) for i in range(len(words) - SHINGLE + 1)}


def corpus_of(values: list) -> str:
    return " | ".join(" ".join(tokens(value)) for value in values)


def found_in(corpus: str, evidence: set) -> int:
    """How many shingles occur in the corpus, matched on whole tokens ("a" is not in "an")."""
    padded = " " + corpus + " "
    return sum(" " + shingle + " " in padded for shingle in evidence)


def lead(text: str) -> str:
    return " ".join(text.split()[:QUERY_WORDS])


# --- one trial's plan ------------------------------------------------------------------


def make_trial(seed: int) -> dict:
    rng = random.Random("stageC-{}".format(seed))
    while True:
        question_id = rng.choice(ELIGIBLE)
        entry = PARSED[question_id]
        keys = list(entry["memories"])
        chosen = sorted(rng.sample(range(len(keys)), min(TURNS, len(keys))))
        keys = [keys[i] for i in chosen]
        texts = [entry["memories"][key].strip() for key in keys]
        sessions, speaker_of = [], {}
        for key in keys:
            session = key.split(":")[0]
            if session not in speaker_of:
                speaker_of[session] = MEMBERS[len(speaker_of) % 2]
            sessions.append(session)
        sets = [shingles(text) for text in texts]
        count = {}
        for one in sets:
            for shingle in one:
                count[shingle] = count.get(shingle, 0) + 1
        distinct = [sorted(s for s in one if count[s] == 1) for one in sets]
        retractable = [i for i in range(len(texts)) if len(distinct[i]) >= MIN_DISTINCT]
        if retractable:
            break
    retract = sorted(rng.sample(retractable, min(rng.randint(*RETRACTIONS), len(retractable))))
    memories, index = [], 0
    while index < len(texts):
        sources = [index]
        if (index + 1 < len(texts) and sessions[index + 1] == sessions[index]
                and rng.random() < PAIR_SHARE):
            sources.append(index + 1)
        memories.append({
            "sources": sources, "speaker": speaker_of[sessions[index]],
            "text": " ".join(texts[i] for i in sources), "session": sessions[index],
        })
        index += len(sources)
    linked = seed % 2 == 1
    links = [
        (a, b) for a, b in zip(range(len(memories)), range(1, len(memories)))
        if memories[a]["session"] == memories[b]["session"]
    ] if linked else []
    touched = {n for n, m in enumerate(memories) if set(m["sources"]) & set(retract)}
    losing = [i for n in sorted(touched) for i in memories[n]["sources"] if i not in retract]
    retained = [i for i in range(len(texts)) if i not in retract]
    others = [i for i in retained if i not in losing]
    queries = [lead(texts[i]) for i in retract] + [entry["question"]]
    queries += [lead(texts[i]) for i in rng.sample(losing, min(3, len(losing)))]
    queries += [lead(texts[i]) for i in rng.sample(others, min(6 - min(3, len(losing)), len(others)))]
    return {
        "seed": seed, "question": question_id, "texts": texts,
        "speakers": [speaker_of[s] for s in sessions], "memories": memories, "links": links,
        "retract": retract, "distinct": distinct, "queries": queries,
        "hybrid": seed % 4 == 3, "linked": linked, "retractable": len(retractable),
    }


# --- building and reading ----------------------------------------------------------------


def build(store: MemoryStore, trial: dict) -> tuple:
    for member in MEMBERS:
        store.join_channel(CHANNEL, member)
    message_ids = [
        store.for_writer(speaker).add_message(text, channel=CHANNEL).id
        for speaker, text in zip(trial["speakers"], trial["texts"])
    ]
    memory_ids = [
        store.for_writer(memory["speaker"]).add_memory(
            memory["text"], MemoryType.FACT, channel=CHANNEL,
            source_message_ids=[message_ids[i] for i in memory["sources"]],
        ).id
        for memory in trial["memories"]
    ]
    for a, b in trial["links"]:
        store.relate(memory_ids[a], memory_ids[b], "related_to")
    return message_ids, memory_ids


def reference_store(trial: dict, embedder) -> MemoryStore:
    store = MemoryStore(":memory:")
    for member in MEMBERS:
        store.join_channel(CHANNEL, member)
    retracted = set(trial["retract"])
    ids, posted = {}, {}
    for number, (speaker, text) in enumerate(zip(trial["speakers"], trial["texts"])):
        if number not in retracted:
            posted[number] = store.for_writer(speaker).add_message(text, channel=CHANNEL).id
    for number, memory in enumerate(trial["memories"]):
        remaining = [i for i in memory["sources"] if i not in retracted]
        if remaining:
            ids[number] = store.for_writer(memory["speaker"]).add_memory(
                " ".join(trial["texts"][i] for i in remaining), MemoryType.FACT,
                channel=CHANNEL, source_message_ids=[posted[i] for i in remaining],
            ).id
    for a, b in trial["links"]:
        if a in ids and b in ids:
            store.relate(ids[a], ids[b], "related_to")
    store.embedder = embedder
    return store


def read_panel(store: MemoryStore, trial: dict) -> list:
    panel = []
    for query in trial["queries"]:
        results = store.search(query, limit=DEPTH, viewers=list(MEMBERS), record_access=False)
        labels = {r.memory.id: r.memory.content for r in results}
        for r in results:
            for link in r.links:
                for end in (link.source_id, link.target_id):
                    if end not in labels:
                        found = store.get_memory(end)
                        labels[end] = found.content if found else "?missing"
        panel.append(stageb.view_of(results, labels))
    return panel


def compare(built: list, reference: list) -> str:
    """identical, same-ranking (same memories in order, scores or links differ) or different."""
    if [v["label"] for v in built] != [v["label"] for v in reference]:
        return "different"
    klass, _ = stageb.compare(built, reference)
    return "identical" if klass == "exact" else "same-ranking"


def leaked(trial: dict, evidence: set, store: MemoryStore, panel: list, message_ids: list) -> bool:
    texts = [view["label"] for views in panel for view in views]
    texts += [m.content for m in store.list_memories(limit=BIG, viewers=list(MEMBERS))]
    for number in range(len(message_ids)):
        message = store.get_message(message_ids[number], viewers=list(MEMBERS))
        if message is not None and message.content:
            texts.append(message.content)
    return found_in(corpus_of(texts), evidence) > 0


# --- faults ---------------------------------------------------------------------------------


@contextlib.contextmanager
def fault(name):
    if name != "keep-text":
        yield
        return
    original = MemoryStore.retract_message

    def keep_text(store, message_id, *, actor_id):
        with store._transaction(write=False) as connection:
            kept = {
                row["id"]: row["content"]
                for row in connection.execute(
                    "SELECT memories.id, memories.content FROM memories "
                    "JOIN memory_sources ON memory_sources.memory_id = memories.id "
                    "WHERE memory_sources.message_id = ?", (message_id,))
            }
        original(store, message_id, actor_id=actor_id)
        with store._transaction() as connection:
            for memory_id, content in kept.items():
                connection.execute("UPDATE memories SET content = ? WHERE id = ?", (content, memory_id))

    with mock.patch.object(MemoryStore, "retract_message", keep_text):
        yield


def retract_all(store: MemoryStore, trial: dict, message_ids: list, flaw=None) -> None:
    for number in trial["retract"]:
        actor = trial["speakers"][number]
        if flaw == "keep-pads" and store.key_path is not None:
            saved, store.key_path = store.key_path, None
            try:
                store.retract_message(message_ids[number], actor_id=actor)
            finally:
                store.key_path = saved
        else:
            store.retract_message(message_ids[number], actor_id=actor)


def consolidator(trial: dict, flaw=None):
    extractive = ExtractiveConsolidator()
    if flaw != "leaky-rebuild":
        return extractive
    leak = " ".join(trial["texts"][trial["retract"][0]].split()[:LEAK_WORDS])

    def leaky(memory, sources):
        return "{} {}".format(extractive(memory, sources), leak)

    return leaky


# --- running one trial ---------------------------------------------------------------------


def run(trial: dict, flaw=None) -> dict:
    retracted = set(trial["retract"])
    evidence = {s for i in retracted for s in trial["distinct"][i]}
    embedder = NGramHashEmbedder() if trial["hybrid"] else None
    result = {"seed": trial["seed"], "hybrid": trial["hybrid"], "linked": trial["linked"],
              "messages": len(trial["texts"]), "retractable": trial["retractable"]}
    dependents = {n for n, m in enumerate(trial["memories"]) if set(m["sources"]) & retracted}
    result["dependents"] = len(dependents)
    expected = {}
    for number in dependents:
        remaining = [i for i in trial["memories"][number]["sources"] if i not in retracted]
        expected[number] = " ".join(trial["texts"][i] for i in remaining) if remaining else None
    result["opportunities"] = sum(text is not None for text in expected.values())

    with tempfile.TemporaryDirectory() as directory, fault(flaw):
        path = Path(directory) / "plain.sqlite3"
        store = MemoryStore(path)
        message_ids, memory_ids = build(store, trial)
        store.embedder = embedder
        read_panel(store, trial)  # creates vectors in hybrid trials
        before = corpus_of(canary.stored_values(store))
        backup = Path(directory) / "backup.sqlite3"
        shutil.copyfile(path, backup)
        backup_bytes = backup.read_bytes()
        prefixes = [trial["texts"][i][:RAW_PREFIX] for i in sorted(retracted)]
        result["probe"] = (found_in(before, evidence) == len(evidence)
                           and all(p.encode() in backup_bytes for p in prefixes))

        retract_all(store, trial, message_ids, flaw)
        after = canary.stored_values(store)
        raw = path.read_bytes()
        erased = found_in(corpus_of(after), evidence) == 0
        if trial["hybrid"]:
            with store._transaction(write=False) as connection:
                kept_vectors = sum(connection.execute(
                    "SELECT COUNT(*) FROM embeddings WHERE memory_id = ?", (memory_ids[n],)
                ).fetchone()[0] for n in dependents)
            erased = erased and kept_vectors == 0
        result["erasure"] = erased
        result["specificity"] = all(
            store.get_message(message_ids[i]).content == trial["texts"][i]
            for i in range(len(message_ids)) if i not in retracted
        ) and all(
            store.get_memory(memory_ids[n]).content == memory["text"]
            for n, memory in enumerate(trial["memories"]) if n not in dependents
        )
        panel_now = read_panel(store, trial)
        reads_ok = not leaked(trial, evidence, store, panel_now, message_ids)

        queued = [memory.id for memory in store.stale_memories()]
        if flaw == "no-rebuild":
            rebuilt_results = {}
        else:
            rebuilt_results = {r.stale_id: r for r in store.rebuild_stale(consolidator(trial, flaw))}
        rebuild = set(rebuilt_results) == set(queued) if flaw != "no-rebuild" else False
        for number in dependents:
            stale_id = memory_ids[number]
            found = rebuilt_results.get(stale_id)
            if expected[number] is not None:
                if found is None or found.rebuilt_id is None:
                    rebuild = False
                    continue
                made = store.get_memory(found.rebuilt_id)
                remaining = sorted(message_ids[i] for i in trial["memories"][number]["sources"]
                                   if i not in retracted)
                if (made.content != expected[number]
                        or sorted(m.id for m in store.sources_of(found.rebuilt_id)) != remaining
                        or found_in(corpus_of([made.content]), evidence)):
                    rebuild = False
            elif found is None or found.rebuilt_id is not None:
                rebuild = False
        unrebuilt = {sid for sid, r in rebuilt_results.items() if r.rebuilt_id is None}
        if flaw != "no-rebuild" and {m.id for m in store.stale_memories()} != unrebuilt:
            rebuild = False
        if found_in(corpus_of(canary.stored_values(store)), evidence):
            rebuild = False
        result["rebuild"] = rebuild

        panel_after = read_panel(store, trial)
        reads_ok = reads_ok and not leaked(trial, evidence, store, panel_after, message_ids)
        reference = reference_store(trial, embedder)
        classes = [compare(a, b) for a, b in zip(panel_after, read_panel(reference, trial))]
        reference.close()
        store.close()
        # Link carryover is part of the never-written equivalence check for
        # both linked and unlinked trials.
        reads_ok = reads_ok and "different" not in classes
        result["reads"] = reads_ok
        result["classes"] = {k: classes.count(k) for k in ("identical", "same-ranking", "different")}
        alone = [trial["texts"][i][:RAW_PREFIX] for i in sorted(retracted)
                 if not any(trial["texts"][i][:RAW_PREFIX] in text
                            for j, text in enumerate(trial["texts"]) if j != i)]
        result["raw_file_still_holds"] = any(p.encode() in raw for p in alone)

    with tempfile.TemporaryDirectory() as directory, fault(flaw):
        path, keys = Path(directory) / "keyed.sqlite3", Path(directory) / "keyed.keys"
        store = MemoryStore(path, key_path=keys)
        message_ids, memory_ids = build(store, trial)
        copy = Path(directory) / "copy.sqlite3"
        shutil.copyfile(path, copy)
        copy_bytes = copy.read_bytes()
        holds_text = any(p.encode() in copy_bytes for p in prefixes)
        retract_all(store, trial, message_ids, flaw)
        old = MemoryStore(copy, key_path=keys)
        recovered = [old.get_message(mid).content or "" for mid in message_ids]
        recovered += [m.content for m in (old.get_memory(mid) for mid in memory_ids) if m is not None]
        readable = all(old.get_message(message_ids[i]).content == trial["texts"][i]
                       for i in range(len(message_ids)) if i not in retracted)
        result["backup"] = (not holds_text and readable
                            and found_in(corpus_of(recovered), evidence) == 0)
        old.close()
        store.close()

    with tempfile.TemporaryDirectory() as directory, fault(flaw):
        store = MemoryStore(Path(directory) / "copies.sqlite3")
        message_ids, memory_ids = build(store, trial)
        copies = [
            store.for_writer(trial["speakers"][number]).add_memory(
                trial["texts"][number], MemoryType.FACT, channel=CHANNEL).id
            for number in sorted(retracted)
        ]
        retract_all(store, trial, message_ids, flaw)
        surviving = sum(
            found_in(corpus_of([store.get_memory(memory_id).content]), evidence) > 0
            for memory_id in copies
        )
        result["copies"] = {"added": len(retracted), "surviving": surviving}
        store.close()
    return result


def run_trial(seed: int, flaw=None) -> dict:
    trial = make_trial(seed)
    first, second = run(trial, flaw), run(trial, flaw)
    result = dict(first)
    result["determinism"] = first == second
    return result


def run_job(job) -> dict:
    return run_trial(*job)


# --- summary, decision, report -----------------------------------------------------------------


def summarise(trials: list) -> dict:
    checks = {
        name: {"held": sum(bool(t[name]) for t in trials),
               "not_held_seeds": [t["seed"] for t in trials if not t[name]]}
        for name in CHECKS
    }
    def tally(select):
        total = {"identical": 0, "same-ranking": 0, "different": 0}
        for t in trials:
            if select(t):
                for key, value in t["classes"].items():
                    total[key] += value
        return total
    opportunity = [t for t in trials if t["opportunities"]]
    return {
        "checks": checks,
        "messages": sum(t["messages"] for t in trials),
        "retractable": sum(t["retractable"] for t in trials),
        "dependents": sum(t["dependents"] for t in trials),
        "opportunities": sum(t["opportunities"] for t in trials),
        "trials_with_opportunity": len(opportunity),
        "unlinked_classes": tally(lambda t: not t["linked"]),
        "linked_classes": tally(lambda t: t["linked"]),
        "families": {name: sum(1 for t in trials if t[name]) for name in ("hybrid", "linked")},
        "raw_file_still_holds": sum(t["raw_file_still_holds"] for t in trials),
        "copies": {key: sum(t["copies"][key] for t in trials) for key in ("added", "surviving")},
        "opportunity_failures": {
            name: sum(not t[name] for t in opportunity) for name in ("rebuild", "reads")
        },
    }


def decide(summary: dict, trials: int) -> dict:
    checks = summary["checks"]
    holds_ = {n: checks[name]["held"] == trials for n, name in RULES.items()}
    failed_controls = [n for n in CONTROL_RULES if not holds_[n]]
    failed_rules = [n for n in BUILT_RULES if not holds_[n]]
    if failed_controls:
        verdict = "inconclusive (control {} failed)".format(", ".join(map(str, failed_controls)))
    elif not failed_rules:
        verdict = "retraction erases on real text"
    else:
        seeds = [s for n in failed_rules for s in checks[RULES[n]]["not_held_seeds"]]
        verdict = "retraction does not erase (rules {} failed, first failing seed {})".format(
            ", ".join(map(str, failed_rules)), min(seeds))
    decision = {"rule_{}_{}".format(n, name): holds_[n] for n, name in RULES.items()}
    decision["verdict"] = verdict
    return decision


def validate_fault(flaw: str, trials: list) -> dict:
    rule = FAULT_RULE[flaw]
    name = RULES[rule]
    scope = trials
    if flaw in FAULT_NEEDS_REBUILD:
        scope = [t for t in trials if t["opportunities"]]
    failed = sum(not t[name] for t in scope)
    share = failed / len(scope) if scope else 0.0
    return {"fault": flaw, "rule": rule, "trials_in_scope": len(scope), "failed": failed,
            "share": share, "detected": bool(scope) and share >= FAULT_SHARE}


def _share(count: int, total: int) -> str:
    return "-" if not total else "{} of {} ({:.1f}%)".format(count, total, 100.0 * count / total)


def render(report: dict) -> str:
    trials, summary, decision = report["trials"], report["summary"], report["decision"]
    checks = summary["checks"]
    lines = [
        "# Retraction on real text",
        "",
        "Real LongMemEval text; no LLM. {} trials (seeds 0 to {}); {} hybrid, {} linked.".format(
            trials, trials - 1, summary["families"]["hybrid"], summary["families"]["linked"]),
        "Store under test: schema version {}{}.".format(
            report["store_schema_version"],
            "; injected fault: {}".format(report["fault"]) if report.get("fault") else ""),
        "See the docstring of `experiments/longmemeval_retraction.py` for the design and rule.",
        "",
        "| Rule | Check | Held in | Needed | Holds |",
        "| --- | --- | --- | --- | --- |",
    ]
    rows = (
        (1, "Determinism: the same seed gives the same result"),
        (2, "Probe: before retraction the scan finds every distinctive shingle (and a backup copy the text)"),
        (3, "Specificity: only memories derived from retracted messages change"),
        (4, "Erasure: no distinctive shingle of a retracted message in any stored value"),
        (5, "Reads: no retracted text readable; reads rank like a store that never got the message"),
        (6, "Rebuild: rebuildable memories rebuilt from exactly their remaining sources"),
        (7, "Backup: with a key file, an earlier copy yields no retracted text"),
    )
    for number, text in rows:
        name = RULES[number]
        lines.append("| {} | {} | {} | every trial | {} |".format(
            number, text, _share(checks[name]["held"], trials),
            decision["rule_{}_{}".format(number, name)]))
    unlinked, linked = summary["unlinked_classes"], summary["linked_classes"]
    lines += [
        "",
        "**Verdict: {}**".format(decision["verdict"]),
        "",
        "Reported, not part of the verdict:",
        "",
        "- Messages sampled {}; retractable (3 or more distinctive shingles): {}.".format(
            summary["messages"], _share(summary["retractable"], summary["messages"])),
        "- Memories derived from a retracted message: {}; of those, with a remaining source to"
        " rebuild from: {} (in {} trials).".format(
            summary["dependents"], summary["opportunities"], summary["trials_with_opportunity"]),
        "- Reads against the never-written reference, per query. Unlinked trials: identical {},"
        " same ranking with other scores {}, different {}. Linked trials (also included in the"
        " reads verdict): identical {}, same ranking {}, different {}.".format(
            unlinked["identical"], unlinked["same-ranking"], unlinked["different"],
            linked["identical"], linked["same-ranking"], linked["different"]),
        "- Trials in which the raw database file still holds the first 40 characters of a"
        " retracted message that no other message shares: {}.".format(_share(summary["raw_file_still_holds"], trials)),
        "- Undeclared copies (memories repeating a retracted message without listing it as a"
        " source): {} written, {} still readable. The store cannot find them; this is a known limit.".format(
            summary["copies"]["added"], summary["copies"]["surviving"]),
        "",
        "Limits: real text, but the derived memories are extractive joins, not model summaries,"
        " and the two-member channel is invented. A model-based consolidator, near-duplicate text,"
        " paraphrased copies and the `record_access` side channel are not tested. Distinctive"
        " shingles define 'its words'; a paraphrase of a retracted message would not be found.",
        "",
    ]
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data", type=Path, default=stageb.DATA)
    parser.add_argument("--trials", type=int, default=DEFAULT_TRIALS)
    parser.add_argument("--jobs", type=int, default=1)
    parser.add_argument("--fault", choices=FAULTS)
    parser.add_argument("--output", type=Path,
                        default=ROOT / "experiments" / "results" / "longmemeval_retraction")
    arguments = parser.parse_args(argv)
    if arguments.trials < 1:
        parser.error("--trials must be positive")
    stageb.install_clock()
    global PARSED, ELIGIBLE
    PARSED = stageb.load(arguments.data)
    ELIGIBLE = sorted(PARSED)
    work = [(seed, arguments.fault) for seed in range(arguments.trials)]
    if arguments.jobs > 1:
        with multiprocessing.get_context("fork").Pool(arguments.jobs) as workers:
            trials = list(workers.imap(run_job, work, chunksize=1))
    else:
        trials = [run_job(job) for job in work]
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
        text += "\nValidation: rule {} failed in {} of {} trials in scope ({:.1f}%): {}.\n".format(
            v["rule"], v["failed"], v["trials_in_scope"], 100 * v["share"],
            "detected" if v["detected"] else "NOT detected")
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.with_suffix(".json").write_text(json.dumps(report, indent=2) + "\n")
    arguments.output.with_suffix(".md").write_text(text)
    print(text)
    stageb.restore_clock()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
