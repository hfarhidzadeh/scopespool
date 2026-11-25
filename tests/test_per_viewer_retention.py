import random
import sqlite3
import tempfile
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from dynmemory import MemoryStore
from dynmemory.store import SCHEMA_VERSION


NOW = datetime(2026, 11, 25, tzinfo=timezone.utc)


def timestamp(at):
    return at.isoformat(timespec="microseconds")


def add_stale(store, text, *, channel="team", **options):
    memory = store.add_memory(text, "fact", channel=channel, speaker="alice", **options)
    store._set_activity(memory.id, created_at=timestamp(NOW - timedelta(days=180)))
    return memory


class PrivateRetentionTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.store = MemoryStore(Path(directory.name) / "memories.db")
        clock = mock.patch.object(self.store, "_now", return_value=timestamp(NOW))
        self.clock = clock.start()
        self.addCleanup(clock.stop)
        self.store.join_channel("team", "alice")
        self.store.join_channel("team", "bob")
        self.store.join_channel("source", "alice")
        self.alice = self.store.for_viewers("alice")
        self.bob = self.store.for_viewers("bob")

    def counters(self):
        with closing(sqlite3.connect(self.store.db_path)) as connection:
            return connection.execute(
                "SELECT member_id, memory_id, access_count, last_accessed_at FROM viewer_access"
            ).fetchall()

    def test_private_opt_in_and_silent_calls(self):
        memory = add_stale(self.store, "launch")
        self.alice.search("launch")
        self.alice.search("launch", record_access=False)
        self.assertEqual(self.counters(), [])
        with self.assertRaisesRegex(ValueError, "single named viewer"):
            self.store.search("launch", record_private_access=True)
        group = self.store.for_viewers(["alice", "bob"])
        with self.assertRaisesRegex(ValueError, "single named viewer"):
            group.search("launch", record_private_access=True)
        with self.assertRaisesRegex(ValueError, "single named viewer"):
            group.list_retained_memories()
        for explicit in (True, False):
            with self.assertRaisesRegex(ValueError, "omit record_access"):
                self.alice.search("launch", record_private_access=True, record_access=explicit)
        self.assertEqual(self.counters(), [])
        self.assertEqual(self.alice.search("missing", record_private_access=True), [])
        self.assertEqual(self.counters(), [])
        expected = self.alice.search("launch")
        self.assertEqual(self.alice.search("launch", record_private_access=True), expected)
        self.assertEqual(self.counters(), [("alice", memory.id, 1, timestamp(NOW))])
        self.assertEqual(self.store.get_memory(memory.id).access_count, 0)
        self.assertEqual(self.alice.list_retained_memories(), [])

    def test_restore_and_expiration(self):
        memory = add_stale(self.store, "launch")
        self.alice.search("launch", record_private_access=True)
        self.store.prune(as_of=NOW, dry_run=False)
        [retained] = self.alice.list_retained_memories()
        self.assertEqual((retained.memory.id, retained.access_count), (memory.id, 1))
        self.store.restore(memory.id)
        self.assertEqual(self.alice.list_retained_memories(), [])
        self.store._set_activity(memory.id, created_at=timestamp(NOW - timedelta(days=180)))
        self.store.prune(as_of=NOW, dry_run=False)
        later = NOW + timedelta(days=90)
        self.clock.return_value = timestamp(later - timedelta(microseconds=1))
        self.assertEqual(len(self.alice.list_retained_memories()), 1)
        self.clock.return_value = timestamp(later)
        self.assertEqual(self.alice.list_retained_memories(), [])
        self.assertEqual(len(self.counters()), 1)
        self.store.prune(as_of=later, dry_run=True)
        self.assertEqual(len(self.counters()), 1)
        self.store.prune(as_of=later, dry_run=False)
        self.assertEqual(self.counters(), [])

    def test_leaving_source_then_rejoining_clears_private_retention(self):
        source = self.store.for_writer("alice").add_message("launch", channel="source")
        memory = add_stale(self.store, "launch from source", source_message_ids=[source.id])
        shared = add_stale(self.store, "another launch")
        self.alice.search("launch", record_private_access=True)
        self.bob.search("launch", record_private_access=True)
        self.store.prune(as_of=NOW, dry_run=False)
        self.assertEqual({x.memory.id for x in self.alice.list_retained_memories()},
                         {memory.id, shared.id})
        self.assertEqual([x.memory.id for x in self.bob.list_retained_memories()], [shared.id])
        self.store.leave_channel("source", "alice")
        self.assertEqual([x.memory.id for x in self.alice.list_retained_memories()], [shared.id])
        self.store.join_channel("source", "alice")
        self.assertEqual([x.memory.id for x in self.alice.list_retained_memories()], [shared.id])
        self.store.leave_channel("team", "alice")
        self.store.join_channel("team", "alice")
        self.assertEqual(self.alice.list_retained_memories(), [])
        self.assertEqual([x.memory.id for x in self.bob.list_retained_memories()], [shared.id])

    def test_retracting_pruned_derivation_erases_its_private_entries(self):
        writer = self.store.for_writer("alice")
        source = writer.add_message("launch", channel="team")
        memory = add_stale(self.store, "launch", source_message_ids=[source.id])
        self.alice.search("launch", record_private_access=True)
        self.bob.search("launch", record_private_access=True)
        self.store.prune(as_of=NOW, dry_run=False)
        self.assertEqual({row[0] for row in self.counters()}, {"alice", "bob"})
        writer.retract_message(source.id)
        self.assertEqual(self.counters(), [])
        self.assertIsNone(self.alice.get_memory(memory.id))
        self.assertEqual(self.alice.list_retained_memories(), [])
        self.assertEqual(self.bob.list_retained_memories(), [])

    def test_a_later_visible_claim_removes_a_pruned_entry(self):
        memory = add_stale(self.store, "launch Tuesday", memory_key="launch-day")
        self.alice.search("launch", record_private_access=True)
        self.store.prune(as_of=NOW, dry_run=False)
        self.assertEqual([x.memory.id for x in self.alice.list_retained_memories()], [memory.id])
        self.store.for_writer("alice").add_memory(
            "launch Wednesday", "fact", channel="team", memory_key="launch-day"
        )
        self.assertEqual(self.alice.list_retained_memories(), [])

    def test_concurrent_increment_and_older_clock_do_not_lose_private_activity(self):
        memory = add_stale(self.store, "launch")
        with ThreadPoolExecutor(max_workers=4) as pool:
            def read(_):
                return self.alice.search("launch", record_private_access=True)

            self.assertTrue(all(pool.map(read, range(12))))
        self.clock.return_value = timestamp(NOW - timedelta(seconds=1))
        self.alice.search("launch", record_private_access=True)
        self.assertEqual(self.counters(), [("alice", memory.id, 13, timestamp(NOW))])

    def test_upgrade_from_schema_7_preserves_shared_activity(self):
        # Capture the complete schema with all pre-existing indexes, and construct
        # a version 7 database without the two new storage fields.
        with closing(sqlite3.connect(self.store.db_path)) as source:
            statements = source.execute(
                "SELECT sql FROM sqlite_master WHERE sql IS NOT NULL AND name NOT LIKE 'viewer_access%' "
                "ORDER BY type = 'index', name"
            ).fetchall()
        legacy_path = Path(self.store.db_path).with_name("legacy.db")
        with closing(sqlite3.connect(legacy_path)) as legacy:
            for (statement,) in statements:
                legacy.execute(statement.replace(", pruned_at TEXT", ""))
            legacy.execute("PRAGMA user_version = 7")
            legacy.execute("INSERT INTO channel_members VALUES ('team', 'alice', ?, NULL)",
                           (timestamp(NOW),))
            for memory_id, archived in (("old", timestamp(NOW)), ("active", None)):
                legacy.execute(
                    """INSERT INTO memories (id, kind, content, source, confidence, importance,
                        created_at, updated_at, access_count, last_accessed_at, channel, archived_at)
                        VALUES (?, 'fact', 'launch', 'fixture', 0.8, 0.5, ?, ?, 4, ?, 'team', ?)""",
                    (memory_id, timestamp(NOW), timestamp(NOW), timestamp(NOW), archived),
                )
            legacy.commit()
        upgraded = MemoryStore(legacy_path)
        alice = upgraded.for_viewers("alice")
        self.assertEqual(alice.get_memory("old").access_count, 4)
        self.assertEqual(alice.get_memory("active").last_accessed_at, timestamp(NOW))
        self.assertEqual(alice.list_retained_memories(), [])
        with closing(sqlite3.connect(legacy_path)) as legacy:
            self.assertEqual(legacy.execute("PRAGMA user_version").fetchone()[0], SCHEMA_VERSION)
            self.assertEqual(legacy.execute("SELECT COUNT(*) FROM viewer_access").fetchone()[0], 0)
            self.assertIsNone(legacy.execute("SELECT pruned_at FROM memories WHERE id = 'old'").fetchone()[0])


class PrivateRetentionComparison(unittest.TestCase):
    @staticmethod
    def run_trial(seed, track):
        rng = random.Random(seed)
        query = "topic{}".format(rng.randrange(8))
        fixtures = [(1, query + " launch", "team", 0.2),
                    (2, "other update", "team", 0.95),
                    (3, query + " operations", "ops", 0.95)]
        rng.shuffle(fixtures)
        with MemoryStore(":memory:") as store, mock.patch.object(store, "_now", return_value=timestamp(NOW)):
            for channel, member in (("team", "alice"), ("team", "bob"), ("ops", "carol")):
                store.join_channel(channel, member)
            for identity, text, channel, importance in fixtures:
                with mock.patch("dynmemory.store.uuid.uuid4", return_value=uuid.UUID(int=identity)):
                    add_stale(store, text, channel=channel, importance=importance)
            alice = store.for_viewers("alice")
            observers = [store.for_viewers(viewers) for viewers in ("bob", "carol", ["alice", "bob"])]
            alice.search(query, record_private_access=track)
            previews = store.prune(as_of=NOW)
            before = [reader.search(query) for reader in observers]
            archived = store.prune(as_of=NOW, dry_run=False)
            identity = uuid.UUID(int=1).hex
            after = [(reader.search(query), reader.history(identity), reader.list_memories())
                     for reader in observers]
            other_retained = [reader.list_retained_memories() for reader in observers[:2]]
            return (previews, before, archived, after, other_retained), alice.list_retained_memories()

    def test_private_retention_across_500_paired_trials(self):
        for seed in range(500):
            with self.subTest(seed=seed):
                observed, tracked = self.run_trial(seed, track=True)
                control, silent = self.run_trial(seed, track=False)
                self.assertEqual(observed, control)
                self.assertEqual(len(observed[2]), 1)
                self.assertEqual(observed[-1], [[], []])
                self.assertEqual(silent, [])
                self.assertEqual(len(tracked), 1)
                self.assertEqual(tracked[0].memory, observed[2][0].memory)
                self.assertEqual(tracked[0].access_count, 1)
