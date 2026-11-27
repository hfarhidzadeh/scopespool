"""Grouped prune scans and JSON-read candidates keep every prune result identical.

The reference is the store module as committed before the change
(``REFERENCE``). Both stores read copies of the same random database and key
files, so any difference comes from how prune reads and builds its results.
Results are compared by ``repr``, which shows types and exact floats; applied
prunes are also compared by dumping both databases. Mutated copies of the
current module (planted faults) show that the comparison catches confidence
taken from the wrong column, a group that drops confidence, rounded floats and
a pad looked up under the wrong key.
"""

import importlib.util
import random
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from dynmemory import MemoryStore, store as current

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = "f74a30c"
WORDS = (
    "launch billing sqlite invoice deploy budget review alpha beta gamma river "
    "planner schema backup token audit retention cache ledger vendor roadmap"
).split()
ODD_TEXT = ('quote " back \\ slash', "tab\tnew\nline", "nul\x00byte", "emoji \U0001F600 café",
            "sep    ", "[1, 2] {\"json\": true}")
KINDS = ("fact", "episode", "task", "correction", "user_preference")
AS_OF = datetime(2026, 11, 26, tzinfo=timezone.utc)
NOW = AS_OF.isoformat(timespec="microseconds")
OLD_ACCESS = (AS_OF - timedelta(days=200)).isoformat(timespec="microseconds")
PARAMETERS = (
    {},
    {"threshold": 0.4, "min_age_days": 0, "protect_importance": None},
    {"threshold": 0.25, "decay_days": 30, "decay_days_by_kind": {"episode": 7, "task": 400},
     "protect_importance": 0.5},
    {"threshold": 1.0, "min_age_days": 10, "as_of": AS_OF - timedelta(days=60)},
)


def load_module(source, name):
    directory = Path(tempfile.mkdtemp(prefix="prune_details_"))
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
    return load_module(source, "prune_details_reference")


REFERENCE_MODULE = load_reference()
CURRENT_SOURCE = Path(current.__file__).read_text(encoding="utf-8")


def stamp(rng):
    return (AS_OF - timedelta(days=rng.uniform(0, 400))).isoformat(timespec="microseconds")


def text(rng):
    words = " ".join(rng.choice(WORDS) for _ in range(rng.randint(2, 7)))
    return words + " " + rng.choice(ODD_TEXT) if rng.random() < 0.25 else words


def unit(rng):
    """Exact floats that JSON text could round, plus the boundaries."""
    return rng.choice((rng.random(), rng.random(), rng.random() / 3, 0.0, 0.5, 0.9, 1.0))


CONFIGURATIONS = [(seed, keyed) for seed in range(6) for keyed in (False, True)]


def build(directory, seed, keyed):
    """Files for one random store: channels, claims, links, retractions, damaged pads."""
    path, key = directory / "store.db", (directory / "keys.db" if keyed else None)
    rng = random.Random("prune-details-{}".format(seed))
    with mock.patch.object(MemoryStore, "_now", return_value=NOW) as clock:
        store = MemoryStore(path, key_path=key)
        for channel, members in (("team", "alice bob carol"), ("side", "alice"), ("dm", "bob")):
            for member in members.split():
                store.join_channel(channel, member)
        store.add_admin("carol")
        messages, ids = [], []
        for _ in range(rng.randint(45, 75)):
            channel = rng.choice(("team", "team", "side", "dm", None))
            speaker = {"side": "alice", "dm": "bob", None: None}.get(
                channel, rng.choice(("alice", "bob", "carol")))
            memory_key, subject = rng.choice((None, None, "k1", "k2", "k3")), None
            if channel and rng.random() < 0.15:
                memory_key, subject = "about-" + speaker, speaker  # a personal fact
            options = {
                "importance": unit(rng), "confidence": unit(rng), "channel": channel,
                "speaker": speaker, "memory_key": memory_key, "fact_subject": subject,
                "source": rng.choice(("conversation", "import")),
            }
            if channel and rng.random() < 0.3:
                message = store.add_message(text(rng), channel=channel, speaker=speaker)
                messages.append((message, speaker))
                memory = store.add_memory(message.content, rng.choice(KINDS),
                                          source_message_ids=[message.id], **options)
            else:
                memory = store.add_memory(text(rng), rng.choice(KINDS), **options)
            ids.append(memory.id)
            store._set_activity(memory.id, created_at=stamp(rng),
                                last_accessed_at=stamp(rng) if rng.random() < 0.4 else None,
                                access_count=rng.choice((0, 0, 1, 3, 17)))
        for _ in range(rng.randint(6, 14)):
            source, target = rng.sample(ids, 2)
            try:
                store.relate(source, target,
                             rng.choice(("related_to", "supports", "contradicts", "supersedes")))
            except ValueError:
                pass
        for message, speaker in rng.sample(messages, min(2, len(messages))):
            store.retract_message(message.id, actor_id=speaker)
        # Private retention rows, some old enough for an applied prune's cleanup.
        for viewer in ("alice", "bob"):
            store.for_viewers(viewer).search("launch budget", record_private_access=True)
        clock.return_value = OLD_ACCESS
        store.for_viewers("alice").search("sqlite ledger", record_private_access=True)
        clock.return_value = NOW
        # Some memories were pruned earlier and are no longer active.
        store.prune(dry_run=False, as_of=AS_OF - timedelta(days=300), threshold=0.02)
        store.close()
    if keyed:
        damaged = rng.sample(ids, 4)
        with closing(sqlite3.connect(key)) as connection, connection:
            connection.execute("DELETE FROM pads WHERE id IN (?, ?)",
                               ("m:" + damaged[0], "m:" + damaged[1]))
            connection.execute("UPDATE pads SET pad = substr(pad, 2) WHERE id = ?",
                               ("m:" + damaged[2],))
    return path, key


def outcome(call):
    """``repr`` of a result (types and exact floats), or the exception a store raised."""
    try:
        return repr(call())
    except Exception as error:  # a mutant may fail instead of differing
        return ("raised", type(error).__name__, str(error))


def copy_files(directory, path, key, name):
    copy = directory / name
    copy.mkdir()
    shutil.copy(path, copy / "store.db")
    if key:
        shutil.copy(key, copy / "keys.db")
    return copy / "store.db", (copy / "keys.db" if key else None)


def dump(path, key):
    with closing(sqlite3.connect(path)) as connection:
        lines = list(connection.iterdump())
    if key:
        with closing(sqlite3.connect(key)) as connection:
            lines += list(connection.iterdump())
    return lines


def differences(module, seed, keyed, json_functions=None):
    """Every place ``module`` disagrees with the reference on one random store."""
    found = []
    with tempfile.TemporaryDirectory() as raw:
        directory = Path(raw)
        path, key = build(directory, seed, keyed)
        with mock.patch.object(REFERENCE_MODULE.MemoryStore, "_now", return_value=NOW), \
                mock.patch.object(module.MemoryStore, "_now", return_value=NOW):
            reference = REFERENCE_MODULE.MemoryStore(path, key_path=key)
            candidate = module.MemoryStore(path, key_path=key)
            if json_functions is not None:
                candidate._json_functions = json_functions
            for index, parameters in enumerate(PARAMETERS):
                arguments = dict({"as_of": AS_OF}, **parameters)
                for details in (True, False):
                    expected = outcome(lambda: reference.prune(details=details, **arguments))
                    actual = outcome(lambda: candidate.prune(details=details, **arguments))
                    if expected != actual:
                        found.append(("preview", index, details))
                applied = []
                for opener, details in ((REFERENCE_MODULE, True), (module, True),
                                        (module, False), (REFERENCE_MODULE, False)):
                    copy_path, copy_key = copy_files(
                        directory, path, key, "copy{}_{}".format(index, len(applied)))
                    store = opener.MemoryStore(copy_path, key_path=copy_key)
                    if opener is module and json_functions is not None:
                        store._json_functions = json_functions
                    result = outcome(lambda: store.prune(dry_run=False, details=details,
                                                         **arguments))
                    applied.append((result, dump(copy_path, copy_key)))
                if applied[0] != applied[1]:
                    found.append(("applied", index, True))
                if applied[2] != applied[3]:
                    found.append(("applied", index, False))
    return found


def mutant(original, replacement, name):
    if CURRENT_SOURCE.count(original) != 1:
        raise AssertionError("mutation target not found exactly once: {}".format(original))
    return load_module(CURRENT_SOURCE.replace(original, replacement), name)


@unittest.skipIf(REFERENCE_MODULE is None,
                 "reference commit {} is not available (shallow clone)".format(REFERENCE))
class PruneDetailsEquivalenceTests(unittest.TestCase):
    def test_results_match_the_reference_in_every_configuration(self):
        for seed, keyed in CONFIGURATIONS:
            with self.subTest(seed=seed, keyed=keyed):
                self.assertEqual(differences(current, seed, keyed), [])

    def test_the_fallback_without_json_functions_matches_too(self):
        for seed, keyed in CONFIGURATIONS[:4]:
            with self.subTest(seed=seed, keyed=keyed):
                self.assertEqual(differences(current, seed, keyed, json_functions=False), [])

    def test_the_fixtures_exercise_what_the_change_touches(self):
        with tempfile.TemporaryDirectory() as raw:
            path, key = build(Path(raw), 1, True)
            with mock.patch.object(MemoryStore, "_now", return_value=NOW):
                store = MemoryStore(path, key_path=key)
                previews = store.prune(as_of=AS_OF, threshold=1.0, min_age_days=0,
                                       protect_importance=None)
                with store._transaction(write=False) as connection:
                    replaced = set(store._claim_view(connection, None).replaced)
            contents = {c.memory.content for c in previews}
            self.assertIn(MemoryStore.UNREADABLE_CONTENT, contents)
            self.assertTrue(any(c.memory.channel is None for c in previews))
            self.assertTrue(any(c.memory.memory_key for c in previews))
            self.assertTrue(any(c.memory.importance != round(c.memory.importance, 12)
                                for c in previews))
            with closing(sqlite3.connect(path)) as connection:
                archived, retracted, private = connection.execute(
                    "SELECT (SELECT COUNT(*) FROM memories WHERE archived_at IS NOT NULL), "
                    "(SELECT COUNT(*) FROM memories WHERE content = ?), "
                    "(SELECT COUNT(*) FROM viewer_access)",
                    (MemoryStore.RETRACTED_CONTENT,)).fetchone()
                active = {row[0] for row in connection.execute(
                    "SELECT id FROM memories WHERE archived_at IS NULL")}
            self.assertGreater(archived, 0)
            self.assertGreater(retracted, 0)
            self.assertGreater(private, 0)
            # Active claims that a read resolves as replaced, which prune skips.
            self.assertTrue(replaced & active)
            self.assertFalse(replaced & {c.memory.id for c in previews})

    def test_confidence_from_the_wrong_column_is_caught(self):
        broken = mutant("confidence=item[-1],", "confidence=item[3],", "prune_details_confidence")
        found = differences(broken, 0, False)
        self.assertIn(("preview", 0, True), found)

    def test_a_group_without_confidence_is_caught(self):
        broken = mutant("GROUP BY importance, confidence", "GROUP BY importance",
                        "prune_details_group")
        found = [d for seed in range(3) for d in differences(broken, seed, False)]
        self.assertTrue(any(item[0] == "preview" for item in found))

    def test_rounded_floats_are_caught(self):
        broken = mutant("importance=item[3],", "importance=round(item[3], 12),",
                        "prune_details_rounded")
        self.assertIn(("preview", 0, True), differences(broken, 0, False))

    def test_a_pad_under_the_wrong_key_is_caught_in_keyed_stores(self):
        broken = mutant('pads.get("m:" + memory_id)', "pads.get(memory_id)",
                        "prune_details_pad_key")
        self.assertEqual(differences(broken, 0, False), [])
        self.assertIn(("preview", 0, True), differences(broken, 0, True))


class PrunePathTests(unittest.TestCase):
    def test_details_read_candidates_without_per_row_helpers(self):
        with tempfile.TemporaryDirectory() as raw:
            path, key = build(Path(raw), 2, True)
            store = MemoryStore(path, key_path=key)
            with mock.patch.object(MemoryStore, "_rows_by_id",
                                   side_effect=AssertionError("per-row read")), \
                    mock.patch.object(MemoryStore, "_memory_from_row",
                                      side_effect=AssertionError("per-row build")), \
                    mock.patch.object(MemoryStore, "_open",
                                      wraps=store._open) as per_row_open:
                previews = store.prune(as_of=AS_OF)
            self.assertTrue(previews)
            self.assertTrue(store._json_functions)
            # Only the claim view (shared with search) opens text one row at a time.
            with closing(sqlite3.connect(path)) as connection:
                keyed_claims = connection.execute(
                    "SELECT COUNT(*) FROM memories WHERE channel IS NOT NULL "
                    "AND memory_key IS NOT NULL AND stale_at IS NULL").fetchone()[0]
            self.assertEqual(per_row_open.call_count, keyed_claims)

    def test_missing_json_functions_select_the_fallback(self):
        class NoJson:
            def execute(self, sql, *args):
                raise sqlite3.OperationalError("no such function: json_group_array")

        store = MemoryStore(":memory:")
        try:
            self.assertFalse(store._has_json_functions(NoJson()))
            self.assertFalse(store._has_json_functions(None))  # remembered, not re-probed
        finally:
            store.close()

    def test_json_builder_matches_memory_from_row_in_this_version(self):
        """Guards against the two builders drifting apart after later edits.

        ``_prune_memories`` rebuilds what ``_memory_from_row`` builds. The
        reference comparison pins both to an earlier commit; this pins them to
        each other in the current code, field by field, so a new ``Memory``
        field or a changed decode fails here.
        """
        import dataclasses
        with tempfile.TemporaryDirectory() as raw:
            store = MemoryStore(Path(raw) / "s.db", key_path=Path(raw) / "k.db")
            try:
                store.join_channel("team", "alice")
                ids = [
                    store.add_memory("plain " + ODD_TEXT[0], "fact").id,
                    store.for_writer("alice").add_memory(
                        ODD_TEXT[3], "fact", channel="team", memory_key="k.one",
                        importance=0.3, confidence=0.1 + 0.2).id,
                ]
                with store._transaction(write=False) as connection:
                    rows = store._rows_by_id(connection, ids)
                    expected = [store._memory_from_row(rows[i]) for i in ids]
                    scored = [(m.id, 0.0, m.kind.value, m.importance, m.created_at,
                               m.confidence) for m in expected]
                    self.assertTrue(store._has_json_functions(connection))
                    actual = store._prune_memories(connection, scored)
                self.assertEqual(len(actual), len(expected))
                for want, got in zip(expected, actual):
                    for field in dataclasses.fields(want):
                        self.assertEqual(repr(getattr(got, field.name)),
                                         repr(getattr(want, field.name)), field.name)
            finally:
                store.close()

    def test_an_empty_store_and_no_candidates(self):
        store = MemoryStore(":memory:")
        try:
            self.assertEqual(store.prune(as_of=AS_OF), [])
            store.add_memory("fresh", "fact")
            self.assertEqual(store.prune(as_of=AS_OF), [])
            self.assertEqual(store.prune(as_of=AS_OF, dry_run=False), [])
        finally:
            store.close()


if __name__ == "__main__":
    unittest.main()
