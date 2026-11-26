"""Shared access counts when events land between ranking and recording."""

import sqlite3
import tempfile
import unittest
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from dynmemory import MemoryStore


NOW = datetime(2026, 11, 25, tzinfo=timezone.utc)
ORIGINAL_RECORD = getattr(MemoryStore, "_record_shared_access", None)
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

    def counts(self):
        with closing(sqlite3.connect(self.store.db_path)) as connection:
            return {
                memory_id: (count, accessed)
                for memory_id, count, accessed in connection.execute(
                    "SELECT id, access_count, last_accessed_at FROM memories"
                )
            }

    def bumped(self):
        return {memory_id for memory_id, (count, _) in self.counts().items() if count}

    def search(self, event=None, *, viewers=True, query="launch", **options):
        """Search with ``event`` run after ranking and before access is recorded."""
        calls = []

        def wrapper(store, memory_ids, viewer_ids, now):
            calls.append((list(memory_ids), viewer_ids))
            if event is not None:
                event()
            recorded = ORIGINAL_RECORD(store, memory_ids, viewer_ids, now)
            calls.append(recorded)
            return recorded

        patch = mock.patch.object(
            MemoryStore, "_record_shared_access", autospec=True, side_effect=wrapper
        )
        with patch as seam:
            if viewers:
                options.setdefault("record_access", True)
                results = self.alice.search(query, **options)
            else:
                results = self.store.search(query, **options)
        return results, calls, seam

    def test_without_an_event_every_returned_memory_is_counted(self):
        first = add_stale(self.store, "launch alpha")
        second = add_stale(self.store, "launch beta", channel="source")
        for viewers, expected_viewers in ((True, ("alice",)), (False, None)):
            with self.subTest(viewers=viewers):
                before = self.counts()
                results, calls, seam = self.search(viewers=viewers)
                returned = [result.memory.id for result in results]
                seam.assert_called_once()
                self.assertEqual(calls[0], (returned, expected_viewers))
                self.assertEqual(calls[1], returned)
                self.assertEqual(set(returned), {first.id, second.id})
                after = self.counts()
                for result in results:
                    self.assertEqual(after[result.memory.id],
                                     (before[result.memory.id][0] + 1, timestamp(NOW)))
                    self.assertEqual(result.memory.access_count, after[result.memory.id][0])

    def test_leaving_a_channel_between_transactions_counts_nothing_there(self):
        hidden = add_stale(self.store, "launch alpha")
        kept = add_stale(self.store, "launch beta", channel="source")
        results, calls, _ = self.search(lambda: self.store.leave_channel("team", "alice"))
        self.assertEqual({result.memory.id for result in results}, {hidden.id, kept.id})
        self.assertEqual(calls[1], [kept.id])
        self.assertEqual(self.bumped(), {kept.id})
        shown = {result.memory.id: result.memory.access_count for result in results}
        self.assertEqual(shown, {hidden.id: 0, kept.id: 1})

    def test_retracting_a_source_between_transactions_counts_nothing_for_it(self):
        writer = self.store.for_writer("alice")
        message = writer.add_message("launch", channel="team")
        derived = add_stale(self.store, "launch alpha", source_message_ids=[message.id])
        kept = add_stale(self.store, "launch beta")
        results, calls, _ = self.search(lambda: writer.retract_message(message.id))
        self.assertEqual({result.memory.id for result in results}, {derived.id, kept.id})
        self.assertEqual(calls[1], [kept.id])
        self.assertEqual(self.bumped(), {kept.id})

    def check_prune_between(self, viewers):
        # Unlike one transaction, the read no longer protects what it returned
        # from a prune that lands before its count is recorded.
        pruned = add_stale(self.store, "launch alpha")
        kept = add_stale(self.store, "launch beta", importance=0.95)
        before = self.counts()
        archived = []
        results, calls, _ = self.search(
            lambda: archived.extend(self.store.prune(as_of=NOW, dry_run=False)),
            viewers=viewers,
        )
        self.assertEqual([candidate.memory.id for candidate in archived], [pruned.id])
        self.assertEqual({result.memory.id for result in results}, {pruned.id, kept.id})
        self.assertEqual(calls[1], [kept.id])
        after = self.counts()
        self.assertEqual(after[pruned.id], before[pruned.id])
        self.assertEqual(after[kept.id], (1, timestamp(NOW)))
        self.assertIsNotNone(self.store.get_memory(pruned.id).archived_at)

    def test_pruning_between_transactions_counts_nothing_for_the_pruned_memory(self):
        self.check_prune_between(viewers=True)

    def test_pruning_between_a_read_without_viewers_and_its_count(self):
        self.check_prune_between(viewers=False)

    def test_ranking_holds_no_write_lock(self):
        add_stale(self.store, "launch alpha")
        for viewers in (False, True):
            with self.subTest(viewers=viewers):
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

                before = sum(count for count, _ in self.counts().values())
                with mock.patch.object(MemoryStore, "_ranked", side_effect=ranked):
                    if viewers:
                        results = self.alice.search("launch", record_access=True)
                    else:
                        results = self.store.search("launch")
                self.assertEqual(len(results), 1)
                self.assertEqual(attempts[:1], ["acquired"])
                self.assertEqual(sum(count for count, _ in self.counts().values()), before + 1)

    def test_no_results_and_silent_reads_never_record(self):
        add_stale(self.store, "launch alpha")
        for viewers, query, options in (
            (True, "missing", {}),
            (False, "missing", {}),
            (False, "launch", {"record_access": False}),
            (True, "launch", {"record_access": False}),
        ):
            with self.subTest(viewers=viewers, query=query, options=options):
                results, _, seam = self.search(viewers=viewers, query=query, **options)
                seam.assert_not_called()
                self.assertEqual(self.bumped(), set())
                self.assertEqual(bool(results), query == "launch")

    def test_private_tracking_does_not_touch_shared_counts(self):
        add_stale(self.store, "launch alpha")
        patch = mock.patch.object(MemoryStore, "_record_shared_access", autospec=True)
        with patch as seam:
            results = self.alice.search("launch", record_private_access=True)
        self.assertEqual(len(results), 1)
        seam.assert_not_called()
        self.assertEqual(self.bumped(), set())

    def test_an_access_recorded_out_of_order_keeps_the_later_time(self):
        memory = add_stale(self.store, "launch alpha")
        later, earlier = timestamp(NOW + timedelta(seconds=5)), timestamp(NOW)
        self.assertEqual(self.store._record_shared_access([memory.id], None, later), [memory.id])
        self.assertEqual(self.store._record_shared_access([memory.id], None, earlier), [memory.id])
        self.assertEqual(self.counts()[memory.id], (2, later))
        self.assertEqual(self.store._record_shared_access([], None, later), [])


if __name__ == "__main__":
    unittest.main()
