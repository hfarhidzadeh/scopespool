"""Private retention when events land between ranking and recording."""

import sqlite3
import tempfile
import unittest
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from dynmemory import MemoryStore


NOW = datetime(2026, 11, 25, tzinfo=timezone.utc)
ORIGINAL_RECORD = getattr(MemoryStore, "_record_private_access", None)
ORIGINAL_RANKED = MemoryStore._ranked


def timestamp(at):
    return at.isoformat(timespec="microseconds")


def add_stale(store, text, *, channel="team", **options):
    memory = store.add_memory(text, "fact", channel=channel, speaker="alice", **options)
    store._set_activity(memory.id, created_at=timestamp(NOW - timedelta(days=180)))
    return memory


class BetweenTransactionTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.store = MemoryStore(Path(directory.name) / "memories.db")
        clock = mock.patch.object(self.store, "_now", return_value=timestamp(NOW))
        clock.start()
        self.addCleanup(clock.stop)
        for channel in ("team", "source"):
            self.store.join_channel(channel, "alice")
        self.store.join_channel("team", "bob")
        self.alice = self.store.for_viewers("alice")

    def rows(self):
        with closing(sqlite3.connect(self.store.db_path)) as connection:
            return {
                memory_id: count
                for memory_id, count in connection.execute(
                    "SELECT memory_id, access_count FROM viewer_access WHERE member_id = 'alice'"
                )
            }

    def between(self, event):
        """Run ``event`` after ranking and before private access is recorded."""
        calls = []

        def wrapper(store, viewer_id, memory_ids, now):
            calls.append(list(memory_ids))
            if event is not None:
                event()
            recorded = ORIGINAL_RECORD(store, viewer_id, memory_ids, now)
            calls.append(recorded)
            return recorded

        patch = mock.patch.object(
            MemoryStore, "_record_private_access", autospec=True, side_effect=wrapper
        )
        return patch, calls

    def search(self, event=None, query="launch"):
        patch, calls = self.between(event)
        with patch as seam:
            results = self.alice.search(query, record_private_access=True)
        return results, calls, seam

    def test_without_an_event_every_returned_memory_is_recorded(self):
        first, second = add_stale(self.store, "launch alpha"), add_stale(self.store, "launch beta")
        results, calls, seam = self.search()
        returned = [result.memory.id for result in results]
        self.assertEqual(set(returned), {first.id, second.id})
        self.assertEqual(seam.call_count, 1)
        self.assertEqual(calls[0], returned)
        self.assertEqual(sorted(calls[1]), sorted(returned))
        self.assertEqual(self.rows(), {first.id: 1, second.id: 1})

    def test_leaving_a_channel_between_transactions_records_nothing_for_it(self):
        hidden = add_stale(self.store, "launch alpha", channel="source")
        kept = add_stale(self.store, "launch beta")
        results, calls, _ = self.search(lambda: self.store.leave_channel("source", "alice"))
        self.assertEqual({result.memory.id for result in results}, {hidden.id, kept.id})
        self.assertEqual(calls[1], [kept.id])
        self.assertEqual(self.rows(), {kept.id: 1})

    def test_leaving_a_source_channel_between_transactions_records_nothing_for_it(self):
        message = self.store.for_writer("alice").add_message("launch", channel="source")
        derived = add_stale(self.store, "launch alpha", source_message_ids=[message.id])
        kept = add_stale(self.store, "launch beta")
        results, calls, _ = self.search(lambda: self.store.leave_channel("source", "alice"))
        self.assertEqual({result.memory.id for result in results}, {derived.id, kept.id})
        self.assertEqual(self.rows(), {kept.id: 1})

    def test_retracting_a_source_between_transactions_records_nothing_for_it(self):
        writer = self.store.for_writer("alice")
        message = writer.add_message("launch", channel="team")
        derived = add_stale(self.store, "launch alpha", source_message_ids=[message.id])
        kept = add_stale(self.store, "launch beta")
        results, calls, _ = self.search(lambda: writer.retract_message(message.id))
        self.assertEqual({result.memory.id for result in results}, {derived.id, kept.id})
        self.assertEqual(calls[1], [kept.id])
        self.assertEqual(self.rows(), {kept.id: 1})

    def test_pruning_between_transactions_still_retains_the_read_memory(self):
        # Same outcome as the read finishing before the prune: the pruned
        # memory lands on the reader's personal list.
        pruned = add_stale(self.store, "launch alpha")
        kept = add_stale(self.store, "launch beta", importance=0.95)
        archived = []
        results, calls, _ = self.search(
            lambda: archived.extend(self.store.prune(as_of=NOW, dry_run=False))
        )
        self.assertEqual([candidate.memory.id for candidate in archived], [pruned.id])
        self.assertEqual({result.memory.id for result in results}, {pruned.id, kept.id})
        self.assertEqual(sorted(calls[1]), sorted([pruned.id, kept.id]))
        self.assertEqual(self.rows(), {pruned.id: 1, kept.id: 1})
        listed = self.alice.list_retained_memories()
        self.assertEqual([item.memory.id for item in listed], [pruned.id])

    def test_an_archive_that_is_not_a_prune_records_nothing(self):
        archived = add_stale(self.store, "launch alpha")
        kept = add_stale(self.store, "launch beta")

        def archive():
            with closing(sqlite3.connect(self.store.db_path)) as connection, connection:
                connection.execute(
                    "UPDATE memories SET archived_at = ? WHERE id = ?",
                    (timestamp(NOW), archived.id),
                )

        results, calls, _ = self.search(archive)
        self.assertEqual({result.memory.id for result in results}, {archived.id, kept.id})
        self.assertEqual(calls[1], [kept.id])
        self.assertEqual(self.rows(), {kept.id: 1})

    def test_superseding_between_transactions_matches_reading_first(self):
        # A channel supersession archives nothing; the claim view hides the
        # older memory at read time, including from the personal list.
        older = self.store.add_memory("launch alpha", "fact", channel="team", speaker="alice")
        newer = self.store.add_memory("launch alpha moved", "fact", channel="team", speaker="alice")
        results, calls, _ = self.search(
            lambda: self.store.relate(newer.id, older.id, "supersedes")
        )
        self.assertEqual({result.memory.id for result in results}, {older.id, newer.id})
        self.assertEqual(sorted(calls[1]), sorted([older.id, newer.id]))
        self.assertEqual([r.memory.id for r in self.alice.search("launch")], [newer.id])

    def test_ranking_holds_no_write_lock(self):
        add_stale(self.store, "launch alpha")
        attempts = []

        def ranked(scores, memories):
            if not attempts:
                with closing(sqlite3.connect(self.store.db_path, timeout=0)) as other:
                    try:
                        other.execute("BEGIN IMMEDIATE")
                        other.execute("ROLLBACK")
                        attempts.append("acquired")
                    except sqlite3.OperationalError as error:
                        attempts.append(str(error))
            return ORIGINAL_RANKED(scores, memories)

        with mock.patch.object(MemoryStore, "_ranked", side_effect=ranked):
            results = self.alice.search("launch", record_private_access=True)
        self.assertEqual(len(results), 1)
        self.assertEqual(attempts[:1], ["acquired"])
        self.assertEqual(len(self.rows()), 1)

    def test_no_results_never_records(self):
        add_stale(self.store, "launch alpha")
        results, _, seam = self.search(query="missing")
        self.assertEqual(results, [])
        seam.assert_not_called()
        self.assertEqual(self.rows(), {})


if __name__ == "__main__":
    unittest.main()
