"""The lean scan returns exactly what the full scan it replaced returned.

Search and prune build full memories only for their results. The reference is
the store module as committed before that change (``REFERENCE``); both stores
read the same database file, so the comparison isolates the scan.
"""

import dataclasses
import importlib.util
import random
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from unittest import mock

from dynmemory import MemoryStore, NGramHashEmbedder

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = "8140298"
SEEDS = range(12)
WORDS = (
    "launch billing sqlite invoice deploy budget review alpha beta gamma river "
    "planner schema backup token audit retention cache ledger vendor roadmap "
    "incident pager metric quota storage report draft summary"
).split()
KINDS = ("fact", "episode", "task", "user_preference", "technical_constraint", "correction")
AS_OF = datetime(2026, 11, 26, tzinfo=timezone.utc)
VIEWERS = (None, ("alice",), ("bob",), ("carol",), ("alice", "bob"))


def load_reference():
    """The committed store module, or None when that commit is not available."""
    try:
        source = subprocess.run(
            ["git", "-C", str(ROOT), "show", "{}:src/dynmemory/store.py".format(REFERENCE)],
            check=True, capture_output=True, text=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        return None
    directory = Path(tempfile.mkdtemp(prefix="lean_reference_"))
    path = directory / "reference_store.py"
    path.write_text(source, encoding="utf-8")
    name = "dynmemory._lean_scan_reference"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


REFERENCE_MODULE = load_reference()


def plain(value):
    """A comparable value with no classes from either store module."""
    if isinstance(value, Enum):
        return value.value
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return tuple(plain(getattr(value, field.name)) for field in dataclasses.fields(value))
    if isinstance(value, (tuple, list)):
        return tuple(plain(item) for item in value)
    return value


def stamp(rng):
    return (AS_OF - timedelta(days=rng.randint(0, 400), seconds=rng.randint(0, 3))).isoformat(
        timespec="microseconds")


def text(rng, low=2, high=9):
    return " ".join(rng.choice(WORDS) for _ in range(rng.randint(low, high)))


def build(store, seed):
    """A random store with channels, claims, sources, retractions, links and activity."""
    rng = random.Random("lean-{}".format(seed))
    for channel, members in (("team", "alice bob carol"), ("side", "alice bob"), ("dm", "bob carol")):
        for member in members.split():
            store.join_channel(channel, member)
    store.add_admin("carol")
    memories, messages, shared_stamp = [], [], stamp(rng)
    for _ in range(rng.randint(40, 90)):
        roll = rng.random()
        channel = rng.choice(("team", "side", "dm", None))
        speaker = rng.choice(("alice", "bob", "carol")) if channel else None
        options = {"importance": round(rng.random(), 3), "confidence": round(rng.random(), 3)}
        try:
            if roll < 0.2 and channel:
                message = store.add_message(text(rng), channel=channel, speaker=speaker)
                messages.append((message, speaker))
                memory = store.add_memory(
                    message.content, rng.choice(KINDS), channel=channel, speaker=speaker,
                    source_message_ids=[message.id], **options)
            elif roll < 0.35 and channel:
                memory = store.add_memory(
                    text(rng, 1, 4), "fact", channel=channel, speaker=speaker,
                    memory_key="k{}".format(rng.randint(0, 3)), **options)
            elif roll < 0.42 and memories:
                memory = store.add_memory(rng.choice(memories).content, rng.choice(KINDS),
                                          channel=channel, speaker=speaker, **options)
            else:
                memory = store.add_memory(text(rng), rng.choice(KINDS), channel=channel,
                                          speaker=speaker, **options)
        except ValueError:
            continue
        memories.append(memory)
        when = shared_stamp if rng.random() < 0.15 else stamp(rng)
        accessed = stamp(rng) if rng.random() < 0.4 else None
        store._set_activity(memory.id, created_at=when, last_accessed_at=accessed,
                            access_count=rng.randint(0, 5))
    relations = ("related_to", "supports", "contradicts", "depends_on", "supersedes")
    for _ in range(rng.randint(10, 30)):
        source, target = rng.sample(memories, 2)
        try:
            store.relate(source.id, target.id, rng.choice(relations))
        except ValueError:
            pass
    for message, speaker in rng.sample(messages, min(len(messages), rng.randint(0, 3))):
        store.retract_message(message.id, actor_id=speaker)


def queries(seed):
    rng = random.Random("lean-queries-{}".format(seed))
    for _ in range(14):
        words = [rng.choice(WORDS) for _ in range(rng.randint(1, 3))]
        if rng.random() < 0.2:
            words.append("unmentioned")
        yield (" ".join(words), rng.choice((None, None, "fact", "episode", "task")),
               rng.choice((1, 3, 10, 40)), rng.choice(VIEWERS))


def configurations():
    for seed in SEEDS:
        yield seed, {
            "embedder": NGramHashEmbedder() if seed % 3 == 1 else None,
            "key": seed % 4 == 2,
            "link_carryover": ("keep", "copy", "topic")[seed % 3],
        }


@unittest.skipIf(REFERENCE_MODULE is None,
                 "reference commit {} is not available (shallow clone)".format(REFERENCE))
class LeanScanEquivalenceTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.directory = Path(directory.name)

    def stores(self, path, config, key_path):
        options = {"link_carryover": config["link_carryover"], "key_path": key_path}
        current = MemoryStore(path, embedder=config["embedder"], **options)
        reference = REFERENCE_MODULE.MemoryStore(path, embedder=config["embedder"], **options)
        return current, reference

    def built(self, seed, config, name="db"):
        path = self.directory / "{}-{}.sqlite3".format(name, seed)
        key_path = str(self.directory / "{}-{}.keys".format(name, seed)) if config["key"] else None
        current, reference = self.stores(path, config, key_path)
        build(current, seed)
        return path, key_path, current, reference

    def test_search_results_are_identical(self):
        compared = nonempty = 0
        for seed, config in configurations():
            _, _, current, reference = self.built(seed, config)
            for query, kind, limit, viewers in queries(seed):
                with self.subTest(seed=seed, query=query, kind=kind, limit=limit, viewers=viewers):
                    options = {"kind": kind, "limit": limit, "viewers": viewers,
                               "record_access": False}
                    expected = plain(reference.search(query, **options))
                    actual = plain(current.search(query, **options))
                    self.assertEqual(actual, expected)
                    compared += 1
                    nonempty += bool(actual)
        self.assertGreater(nonempty, compared // 2)  # the comparison is not vacuous

    def test_prune_previews_are_identical(self):
        candidates = 0
        for seed, config in configurations():
            _, _, current, reference = self.built(seed, config)
            for threshold, protect, by_kind in ((0.1, 0.9, None), (0.5, None, {"task": 10}),
                                                (0.9, 0.5, {"fact": 400, "episode": 3})):
                with self.subTest(seed=seed, threshold=threshold):
                    options = {"threshold": threshold, "protect_importance": protect,
                               "decay_days_by_kind": by_kind, "as_of": AS_OF, "dry_run": True}
                    expected = plain(reference.prune(**options))
                    self.assertEqual(plain(current.prune(**options)), expected)
                    candidates += len(expected)
        self.assertGreater(candidates, 0)

    def test_applied_prune_and_counted_reads_leave_identical_databases(self):
        now = AS_OF.isoformat(timespec="microseconds")
        for seed, config in list(configurations())[:6]:
            path, key_path, _, _ = self.built(seed, config, name="source")
            copies = []
            for label in ("current", "reference"):
                copy = self.directory / "{}-{}.sqlite3".format(label, seed)
                shutil.copy(path, copy)
                copy_key = None
                if key_path is not None:
                    copy_key = str(self.directory / "{}-{}.keys".format(label, seed))
                    shutil.copy(key_path, copy_key)
                copies.append((copy, copy_key))
            current = MemoryStore(copies[0][0], embedder=config["embedder"],
                                  link_carryover=config["link_carryover"], key_path=copies[0][1])
            reference = REFERENCE_MODULE.MemoryStore(
                copies[1][0], embedder=config["embedder"],
                link_carryover=config["link_carryover"], key_path=copies[1][1])
            outcomes = []
            for store in (current, reference):
                with mock.patch.object(store, "_now", return_value=now):
                    reads = [plain(store.search(query, kind=kind, limit=limit, viewers=viewers,
                                                record_access=True))
                             for query, kind, limit, viewers in queries(seed)]
                    pruned = plain(store.prune(threshold=0.5, as_of=AS_OF, dry_run=False))
                with store._transaction(write=False) as connection:
                    rows = [tuple(row) for row in connection.execute(
                        "SELECT * FROM memories ORDER BY id")]
                outcomes.append((reads, pruned, rows))
            with self.subTest(seed=seed):
                self.assertEqual(outcomes[0], outcomes[1])
                self.assertTrue(outcomes[0][1])


class LeanScanBehaviourTests(unittest.TestCase):
    def test_sealed_text_is_opened_for_ranking_and_results(self):
        with tempfile.TemporaryDirectory() as directory:
            store = MemoryStore(Path(directory) / "s.sqlite3",
                                key_path=Path(directory) / "s.keys")
            store.join_channel("team", "alice")
            memory = store.add_memory("sealed launch checklist", "fact", channel="team",
                                      speaker="alice")
            results = store.search("launch", viewers="alice")
            self.assertEqual([r.memory.content for r in results], ["sealed launch checklist"])
            with store._transaction(write=False) as connection:
                stored = connection.execute(
                    "SELECT content FROM memories WHERE id = ?", (memory.id,)).fetchone()[0]
            self.assertNotIn("launch", stored)

    def test_results_are_full_memories_and_ranking_rows_are_not_returned(self):
        with MemoryStore(":memory:") as store:
            memory = store.add_memory("billing endpoint v2", "fact", importance=0.7)
            result = store.search("billing", record_access=False)[0]
        self.assertEqual(result.memory, memory)
        self.assertEqual(type(result.memory).__name__, "Memory")


if __name__ == "__main__":
    unittest.main()
