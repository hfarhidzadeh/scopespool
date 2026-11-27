"""Sparse vector scoring, batched pads and lightweight prune keep results identical.

The reference is the store module as committed before these changes
(``REFERENCE``). Both stores read the same database and key files, so any
difference comes from the scoring and decryption paths. Mutated copies of the
current module show that the comparison catches a dropped query dimension and
a misaligned pad.
"""

import dataclasses
import importlib.util
import random
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
import zlib
from contextlib import closing
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from unittest import mock

from dynmemory import MemoryStore, NGramHashEmbedder, store as current

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = "47e4489"
WORDS = (
    "launch billing sqlite invoice deploy budget review alpha beta gamma river "
    "planner schema backup token audit retention cache ledger vendor roadmap"
).split()
KINDS = ("fact", "episode", "task", "correction")
AS_OF = datetime(2026, 11, 26, tzinfo=timezone.utc)
NOW = AS_OF.isoformat(timespec="microseconds")
VIEWERS = (None, ("alice",), ("bob",), ("alice", "bob"))


def load_module(source, name):
    directory = Path(tempfile.mkdtemp(prefix="speedups_"))
    path = directory / "{}.py".format(name)
    path.write_text(source, encoding="utf-8")
    full = "dynmemory._{}".format(name)
    spec = importlib.util.spec_from_file_location(full, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[full] = module
    spec.loader.exec_module(module)
    return module


def load_reference():
    try:
        source = subprocess.run(
            ["git", "-C", str(ROOT), "show", "{}:src/dynmemory/store.py".format(REFERENCE)],
            check=True, capture_output=True, text=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        return None
    return load_module(source, "speedups_reference")


REFERENCE_MODULE = load_reference()
CURRENT_SOURCE = Path(current.__file__).read_text(encoding="utf-8")


class DenseEmbedder:
    """Deterministic 64-dimension vectors with almost no zero components."""

    name = "test-dense:64"

    def __init__(self, min_similarity=0.05):
        self.min_similarity = min_similarity

    def __call__(self, texts):
        vectors = []
        for text in texts:
            vector = [0.0] * 64
            for word in text.lower().split():
                seed = zlib.crc32(word.encode("utf-8"))
                for index in range(64):
                    seed = (seed * 1103515245 + 12345) & 0x7FFFFFFF
                    vector[index] += (seed % 2001 - 1000) / 1000.0
            vectors.append(vector)
        return vectors


def plain(value):
    if isinstance(value, Enum):
        return value.value
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return tuple(plain(getattr(value, field.name)) for field in dataclasses.fields(value))
    if isinstance(value, (tuple, list)):
        return tuple(plain(item) for item in value)
    return value


def stamp(rng):
    return (AS_OF - timedelta(days=rng.randint(0, 400))).isoformat(timespec="microseconds")


def text(rng, low=2, high=8):
    return " ".join(rng.choice(WORDS) for _ in range(rng.randint(low, high)))


def embedder_for(name):
    return {
        None: None,
        "ngram": NGramHashEmbedder(),
        "ngram-all": NGramHashEmbedder(min_similarity=-1.0),
        "dense": DenseEmbedder(),
    }[name]


CONFIGURATIONS = [
    (seed, embedder, keyed)
    for seed, (embedder, keyed) in enumerate(
        (e, k) for e in (None, "ngram", "ngram-all", "dense") for k in (False, True)
    )
]


def build(directory, seed, embedder, keyed):
    """Files for one random store, with vectors written and some pads damaged."""
    path, key = directory / "store.db", (directory / "keys.db" if keyed else None)
    rng = random.Random("speedups-{}".format(seed))
    with mock.patch.object(MemoryStore, "_now", return_value=NOW):
        store = MemoryStore(path, key_path=key, embedder=embedder_for(embedder))
        for channel, members in (("team", "alice bob"), ("side", "alice"), ("dm", "bob")):
            for member in members.split():
                store.join_channel(channel, member)
        messages, ids = [], []
        for _ in range(rng.randint(40, 70)):
            channel = rng.choice(("team", "side", "dm"))
            speaker = "alice" if channel == "side" else ("bob" if channel == "dm" else
                                                       rng.choice(("alice", "bob")))
            options = {"importance": round(rng.random(), 3), "confidence": round(rng.random(), 3)}
            if rng.random() < 0.3:
                message = store.add_message(text(rng), channel=channel, speaker=speaker)
                messages.append((message, speaker))
                memory = store.add_memory(message.content, rng.choice(KINDS), channel=channel,
                                          speaker=speaker, source_message_ids=[message.id],
                                          **options)
            else:
                memory = store.add_memory(text(rng), rng.choice(KINDS), channel=channel,
                                          speaker=speaker, **options)
            ids.append(memory.id)
            store._set_activity(memory.id, created_at=stamp(rng),
                                last_accessed_at=stamp(rng) if rng.random() < 0.4 else None,
                                access_count=rng.randint(0, 4))
        for _ in range(rng.randint(5, 15)):
            source, target = rng.sample(ids, 2)
            try:
                store.relate(source, target, rng.choice(("related_to", "supports", "contradicts")))
            except ValueError:
                pass
        for message, speaker in rng.sample(messages, min(2, len(messages))):
            store.retract_message(message.id, actor_id=speaker)
        if embedder is not None:
            store.search("launch", record_access=False)  # writes every missing vector
        store.close()
    if keyed:
        damaged = rng.sample(ids, 6)
        with closing(sqlite3.connect(key)) as connection, connection:
            model = embedder_for(embedder).name if embedder else "none"
            connection.execute("DELETE FROM pads WHERE id IN (?, ?)",
                               ("m:" + damaged[0], "v:{}:{}".format(damaged[1], model)))
            for key_id in ("m:" + damaged[2], "v:{}:{}".format(damaged[3], model)):
                connection.execute("UPDATE pads SET pad = substr(pad, 2) WHERE id = ?", (key_id,))
    return path, key


def open_store(module, path, key, embedder):
    store = module.MemoryStore(path, key_path=key, embedder=embedder_for(embedder))
    return store


def query_set(seed):
    rng = random.Random("speedups-queries-{}".format(seed))
    for _ in range(10):
        words = [rng.choice(WORDS) for _ in range(rng.randint(1, 3))]
        if rng.random() < 0.2:
            words.append("unreadable")
        yield " ".join(words), rng.choice((None, "fact", "task")), rng.choice((3, 10, 40))


def outcome(call):
    """A comparable result, or the exception type a broken store raised."""
    try:
        return plain(call())
    except Exception as error:  # a mutant may fail to decode instead of differing
        return ("raised", type(error).__name__)


def differences(module, seed, embedder, keyed):
    """Every place ``module`` disagrees with the reference on one random store."""
    found = []
    with tempfile.TemporaryDirectory() as raw:
        directory = Path(raw)
        path, key = build(directory, seed, embedder, keyed)
        with mock.patch.object(REFERENCE_MODULE.MemoryStore, "_now", return_value=NOW), \
                mock.patch.object(module.MemoryStore, "_now", return_value=NOW):
            reference = open_store(REFERENCE_MODULE, path, key, embedder)
            candidate = open_store(module, path, key, embedder)
            for query, kind, limit in query_set(seed):
                for viewers in VIEWERS:
                    arguments = dict(kind=kind, limit=limit, record_access=False,
                                     viewers=list(viewers) if viewers else None)
                    expected = plain(reference.search(query, **arguments))
                    actual = outcome(lambda: candidate.search(query, **arguments))
                    if expected != actual:
                        found.append(("search", query, viewers))
            full = reference.prune(dry_run=True, as_of=AS_OF)
            if outcome(lambda: candidate.prune(dry_run=True, as_of=AS_OF)) != plain(full):
                found.append(("prune details",))
            summaries = tuple(
                (c.memory.id, c.score, c.memory.kind.value, c.memory.importance,
                 c.memory.last_accessed_at or c.memory.created_at) for c in full)
            if outcome(lambda: candidate.prune(dry_run=True, as_of=AS_OF, details=False)) \
                    != summaries:
                found.append(("prune summaries",))
            dumps = []
            for opener, options in ((REFERENCE_MODULE, {}), (module, {}),
                                    (module, {"details": False})):
                copy = directory / "copy{}".format(len(dumps))
                copy.mkdir()
                shutil.copy(path, copy / "store.db")
                if key:
                    shutil.copy(key, copy / "keys.db")
                applied = open_store(opener, copy / "store.db",
                                     copy / "keys.db" if key else None, embedder)
                outcome(lambda: applied.prune(dry_run=False, as_of=AS_OF, **options))
                with closing(sqlite3.connect(copy / "store.db")) as connection:
                    dumps.append(list(connection.iterdump()))
            if not dumps[0] == dumps[1] == dumps[2]:
                found.append(("applied prune",))
    return found


def mutant(original, replacement, name):
    if CURRENT_SOURCE.count(original) != 1:
        raise AssertionError("mutation target not found exactly once: {}".format(original))
    return load_module(CURRENT_SOURCE.replace(original, replacement), name)


@unittest.skipIf(REFERENCE_MODULE is None,
                 "reference commit {} is not available (shallow clone)".format(REFERENCE))
class SpeedupEquivalenceTests(unittest.TestCase):
    def test_results_match_the_reference_in_every_configuration(self):
        for seed, embedder, keyed in CONFIGURATIONS:
            with self.subTest(seed=seed, embedder=embedder, keyed=keyed):
                self.assertEqual(differences(current, seed, embedder, keyed), [])

    def test_dropping_one_query_dimension_is_caught(self):
        broken = mutant(
            "if value != 0.0]",
            "if value != 0.0][1:]",
            "speedups_dropped_dimension",
        )
        found = [d for seed, embedder, keyed in CONFIGURATIONS if embedder
                 for d in differences(broken, seed, embedder, keyed)]
        self.assertTrue(any(item[0] == "search" for item in found))

    def test_a_misaligned_pad_is_caught_in_keyed_stores(self):
        broken = mutant(
            'int.from_bytes(sealed, "little") ^ int.from_bytes(pad, "little")',
            'int.from_bytes(sealed, "little") ^ int.from_bytes(pad[1:] + pad[:1], "little")',
            "speedups_misaligned_pad",
        )
        found = [d for seed, embedder, keyed in CONFIGURATIONS if keyed
                 for d in differences(broken, seed, embedder, keyed)]
        self.assertTrue(any(item[0] == "search" for item in found))


class PruneSummaryTests(unittest.TestCase):
    def test_summaries_need_no_content_and_apply_the_same_archive(self):
        with tempfile.TemporaryDirectory() as raw:
            path, key = build(Path(raw), 99, None, True)
            store = MemoryStore(path, key_path=key)
            with mock.patch.object(MemoryStore, "_open", side_effect=AssertionError("read")):
                summaries = store.prune(dry_run=True, as_of=AS_OF, details=False)
            self.assertTrue(summaries)
            self.assertIsInstance(summaries[0], current.PruneSummary)
            applied = store.prune(dry_run=False, as_of=AS_OF, details=False)
            self.assertEqual([s.memory_id for s in applied], [s.memory_id for s in summaries])
            archived = {m.id for m in store.list_memories(limit=1000, include_archived=True)
                        if m.archived_at is not None}
            self.assertTrue({s.memory_id for s in applied} <= archived)


if __name__ == "__main__":
    unittest.main()
