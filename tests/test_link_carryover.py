import contextlib
import io
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dynmemory import Link, LinkCarryover, MemoryStore, MemoryType, Relationship
from dynmemory.cli import main


class LinkCarryoverTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.temp_dir.cleanup()

    def store(self, policy):
        return MemoryStore(
            Path(self.temp_dir.name) / "{}.sqlite3".format(policy), link_carryover=policy
        )

    def cats(self, store):
        """A context memory linked to a fact that is then updated."""
        context = store.add_memory("Luna loves tuna treats.", MemoryType.EPISODE)
        old = store.add_memory("I have three cats.", MemoryType.FACT, memory_key="cats")
        store.relate(context.id, old.id)
        new = store.add_memory("I have four cats now.", MemoryType.FACT, memory_key="cats")
        return context, old, new

    def relationship_count(self, store):
        with store._transaction(write=False) as connection:
            return connection.execute("SELECT COUNT(*) FROM relationships").fetchone()[0]

    def test_keep_leaves_links_on_the_old_version(self):
        store = self.store("keep")
        context, _, _ = self.cats(store)

        results = store.search("tuna", record_access=False)

        self.assertEqual([result.memory.id for result in results], [context.id])
        self.assertEqual(results[0].links, ())

    def test_copy_and_topic_bring_the_link_to_the_new_version(self):
        searches = {}
        for policy in ("copy", "topic"):
            store = self.store(policy)
            context, _, new = self.cats(store)
            results = store.search("tuna", record_access=False)
            by_id = {result.memory.id: result for result in results}
            self.assertEqual(set(by_id), {context.id, new.id}, policy)
            self.assertEqual(by_id[new.id].matched_by, "graph", policy)
            self.assertEqual(
                by_id[new.id].links,
                (Link(context.id, new.id, Relationship.RELATED_TO),),
                policy,
            )
            searches[policy] = [
                (result.memory.content, result.score, result.matched_by) for result in results
            ]
        self.assertEqual(searches["copy"], searches["topic"])

    def test_copy_writes_the_link_and_topic_resolves_it_on_read(self):
        counts = {}
        for policy in ("keep", "copy", "topic"):
            store = self.store(policy)
            self.cats(store)
            counts[policy] = self.relationship_count(store)
        # keep and topic: the context link plus the supersedes link.
        self.assertEqual(counts, {"keep": 2, "copy": 3, "topic": 2})

    def test_carried_links_follow_updates_at_both_ends(self):
        for policy, expected in (("keep", False), ("copy", True), ("topic", True)):
            store = self.store(policy)
            first_a = store.add_memory("alpha first", MemoryType.FACT, memory_key="a")
            first_b = store.add_memory("bravo first", MemoryType.FACT, memory_key="b")
            store.relate(first_a.id, first_b.id, Relationship.DEPENDS_ON)
            second_b = store.add_memory("bravo second", MemoryType.FACT, memory_key="b")
            second_a = store.add_memory("alpha second", MemoryType.FACT, memory_key="a")

            found = {
                result.memory.id for result in store.search("alpha", record_access=False)
            }

            self.assertEqual(found, {second_a.id, second_b.id} if expected else {second_a.id}, policy)

    def test_a_link_between_two_versions_never_becomes_a_self_link(self):
        for policy in ("copy", "topic"):
            store = self.store(policy)
            old = store.add_memory("zulu old claim", MemoryType.FACT)
            new = store.add_memory("zulu new claim", MemoryType.FACT)
            other = store.add_memory("yankee other note", MemoryType.FACT)
            store.relate(new.id, old.id, Relationship.CONTRADICTS)
            store.relate(other.id, old.id, Relationship.SUPPORTS)
            store.relate(new.id, old.id, Relationship.SUPERSEDES)

            by_id = {
                result.memory.id: result
                for result in store.search("yankee zulu", record_access=False)
            }

            # The other link moves to the new version; the link between the two
            # versions does not turn into a link from the new version to itself.
            self.assertEqual(
                by_id[new.id].links, (Link(other.id, new.id, Relationship.SUPPORTS),), policy
            )

    def test_topic_does_not_resolve_to_a_pruned_version(self):
        now = datetime.now(timezone.utc)
        store = self.store("topic")
        context, _, new = self.cats(store)
        self.assertIn(
            new.id, {result.memory.id for result in store.search("tuna", record_access=False)}
        )
        stamp = (now - timedelta(days=300)).isoformat()
        store._set_activity(new.id, created_at=stamp)
        store._set_activity(context.id, created_at=now.isoformat())
        store.prune(dry_run=False, as_of=now, threshold=0.5)
        self.assertIsNotNone(store.get_memory(new.id).archived_at)

        results = store.search("tuna", record_access=False)

        self.assertEqual([(result.memory.id, result.links) for result in results], [(context.id, ())])

    def test_rebuild_carries_a_live_link(self):
        store = self.store("keep")
        removed = store.add_message("the removed source", channel="private", speaker="alice")
        source = store.add_message("the remaining source", channel="private", speaker="alice")
        derived = store.add_memory(
            "the derived summary", MemoryType.EPISODE,
            source_message_ids=[removed.id, source.id],
        )
        context = store.add_memory("context for the summary", MemoryType.EPISODE)
        store.relate(context.id, derived.id, Relationship.RELATED_TO)

        store.retract_message(removed.id, actor_id="alice")
        rebuilt = store.rebuild_stale(
            lambda _stale, messages: " ".join(message.content for message in messages)
        )

        self.assertEqual(len(rebuilt), 1)
        self.assertIsNotNone(rebuilt[0].rebuilt_id)
        result = next(
            item for item in store.search("context", record_access=False)
            if item.memory.id == context.id
        )
        self.assertEqual(
            result.links,
            (Link(context.id, rebuilt[0].rebuilt_id, Relationship.RELATED_TO),),
        )

    def linked_pairs(self, store):
        with store._transaction(write=False) as connection:
            return {
                (row["source_id"], row["target_id"], row["relation"])
                for row in connection.execute(
                    "SELECT source_id, target_id, relation FROM relationships "
                    "WHERE relation != 'supersedes'"
                )
            }

    def two_linked_derivations(self, store):
        """Memories A and B, each from two messages, linked to each other."""
        messages = [
            store.add_message("source {} text".format(number), channel="private", speaker="alice")
            for number in range(4)
        ]
        first = store.add_memory(
            "summary of the first pair", MemoryType.EPISODE,
            source_message_ids=[messages[0].id, messages[1].id])
        second = store.add_memory(
            "summary of the second pair", MemoryType.EPISODE,
            source_message_ids=[messages[2].id, messages[3].id])
        store.relate(first.id, second.id)
        return messages, first, second

    def join_sources(self, _stale, messages):
        return " ".join(message.content for message in messages)

    def test_rebuilding_both_ends_of_a_link_relinks_them_in_either_order(self):
        for order in ((0, 2), (2, 0)):
            with self.subTest(order=order):
                store = MemoryStore(":memory:")
                messages, first, second = self.two_linked_derivations(store)
                for index in order:
                    store.retract_message(messages[index].id, actor_id="alice")
                rebuilt = {r.stale_id: r.rebuilt_id for r in store.rebuild_stale(self.join_sources)}
                self.assertEqual(set(rebuilt), {first.id, second.id})
                self.assertIn(
                    (rebuilt[first.id], rebuilt[second.id], "related_to"),
                    self.linked_pairs(store),
                )

    def test_a_link_to_a_memory_with_no_live_rebuild_is_not_carried(self):
        store = MemoryStore(":memory:")
        messages, first, second = self.two_linked_derivations(store)
        # The second memory loses both of its sources, so it cannot be rebuilt.
        store.retract_message(messages[0].id, actor_id="alice")
        store.retract_message(messages[2].id, actor_id="alice")
        store.retract_message(messages[3].id, actor_id="alice")
        results = {r.stale_id: r.rebuilt_id for r in store.rebuild_stale(self.join_sources)}
        self.assertIsNotNone(results[first.id])
        self.assertIsNone(results[second.id])
        touching = [pair for pair in self.linked_pairs(store) if results[first.id] in pair[:2]]
        self.assertEqual(touching, [])

    def test_a_link_to_an_archived_memory_is_not_carried(self):
        store = MemoryStore(":memory:")
        messages, first, second = self.two_linked_derivations(store)
        with store._transaction() as connection:  # as pruning would
            connection.execute(
                "UPDATE memories SET archived_at = updated_at WHERE id = ?", (second.id,))
        store.retract_message(messages[0].id, actor_id="alice")
        (result,) = store.rebuild_stale(self.join_sources)
        self.assertEqual(
            [pair for pair in self.linked_pairs(store) if result.rebuilt_id in pair[:2]], [])

    def test_a_failure_while_carrying_links_leaves_the_memory_queued(self):
        from unittest import mock

        store = MemoryStore(":memory:")
        messages, first, _ = self.two_linked_derivations(store)
        store.retract_message(messages[0].id, actor_id="alice")
        before = len(store.list_memories(limit=100))
        with mock.patch.object(MemoryStore, "_carry_rebuild_links", side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                store.rebuild_stale(self.join_sources)
        self.assertEqual([memory.id for memory in store.stale_memories()], [first.id])
        self.assertEqual(len(store.list_memories(limit=100)), before)

    def test_unknown_policy_is_rejected(self):
        with self.assertRaises(ValueError):
            MemoryStore(":memory:", link_carryover="move")
        self.assertIs(MemoryStore(":memory:").link_carryover, LinkCarryover.KEEP)

    def test_cli_flag_selects_the_policy(self):
        db = str(Path(self.temp_dir.name) / "cli.sqlite3")
        context, _, new = self.cats(MemoryStore(db))

        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            main(["--db", db, "--link-carryover", "topic", "search", "tuna", "--peek"])

        self.assertEqual(
            {result["memory"]["id"] for result in json.loads(out.getvalue())},
            {context.id, new.id},
        )


if __name__ == "__main__":
    unittest.main()
