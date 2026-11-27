import contextlib
import importlib.util
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from dynmemory import MemoryStore
from dynmemory.evermembench import topic_memories

SCRIPT = Path(__file__).resolve().parents[1] / "experiments" / "evermembench_audience.py"
spec = importlib.util.spec_from_file_location("evermembench_audience", SCRIPT)
audience = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = audience
spec.loader.exec_module(audience)


def message(number, speaker, text):
    return {"message_index": number, "speaker": speaker, "dialogue": text,
            "time": "2025-01-01 09:00:00"}


# Ada posts only in Group 1, Cy only in Group 2, Bo in both.
DAY = {"topic_id": "01", "date": "2025-01-01", "dialogues": {
    "Group 1": [message(1, "Ada", "the launch budget is approved"),
                message(2, "Bo", "launch review moved to friday"),
                message(3, "Ada", "lunch order was pasta")],
    "Group 2": [message(1, "Cy", "launch budget doubled for the vendor"),
                message(2, "Bo", "the vendor contract launch is signed"),
                message(3, "Cy", "weather is nice")],
}}
QUESTIONS = [
    {"topic_id": "01", "id": "q1", "Q": "What happened to the launch budget?",
     "R": [{"date": "2025-01-01", "group": "Group 1", "message_index": "1"},
           {"date": "2025-01-01", "group": "Group 2", "message_index": "1"}]},
    {"topic_id": "01", "id": "q2", "Q": "Was the vendor launch contract signed?",
     "R": [{"date": "2025-01-01", "group": "Group 1", "message_index": "2"},
           {"date": "2025-01-01", "group": "Group 2", "message_index": "2"}]},
    {"topic_id": "01", "id": "q3", "Q": "What was for lunch?",
     "R": [{"date": "2025-01-01", "group": "Group 1", "message_index": "3"}]},
]


def suite():
    return topic_memories([DAY], QUESTIONS)


class AskerTests(unittest.TestCase):
    def test_the_asker_is_in_some_but_not_all_cited_groups_and_is_seeded(self):
        data = suite()
        members = audience.memberships(data)
        self.assertEqual(members["Bo"], {"Group 1", "Group 2"})
        query = data["queries"][0]
        askers = {audience.choose_asker(query, members, seed) for seed in range(20)}
        self.assertEqual(askers, {"Ada", "Cy"})
        self.assertEqual(audience.choose_asker(query, members, 3),
                         audience.choose_asker(query, members, 3))


class RunTests(unittest.TestCase):
    def test_the_current_store_passes_and_only_cross_group_questions_count(self):
        result = audience.run_suite(suite())
        self.assertEqual([row["id"] for row in result["rows"]], ["q1", "q2"])
        for row in result["rows"]:
            self.assertTrue(row["noninterference"] and row["no_hidden"], row)
            self.assertTrue(row["power"], row)
            self.assertTrue(all(key.split("|")[1] in row["asker_groups"] for key in row["full"]))
        summary = audience.summarise([result], audience.check_determinism(suite(), None, None))
        self.assertEqual(audience.decide(summary)["verdict"], "no leak across groups")

    def test_searching_without_viewers_fails_rules_3_and_4(self):
        result = audience.run_suite(suite(), fault="leak")
        summary = audience.summarise([result], True)
        self.assertEqual(len(summary["noninterference_failed"]), 2)
        self.assertEqual(len(summary["no_hidden_failed"]), 2)
        self.assertTrue(audience.validate_fault(summary)["detected"])
        self.assertTrue(audience.decide(summary)["verdict"].startswith("leak (rules 3, 4 failed"))

    def test_a_run_is_a_function_of_its_inputs(self):
        self.assertEqual(audience.run_suite(suite()), audience.run_suite(suite()))
        self.assertTrue(audience.check_determinism(suite(), None, None))


class DecisionTests(unittest.TestCase):
    def summary(self, **changes):
        base = {"questions": 10, "skipped": 0, "determinism": True, "power_held": 3,
                "noninterference_failed": [], "no_hidden_failed": [],
                "all_required_visible": 0.5, "per_topic": {}}
        base.update(changes)
        return base

    def test_verdicts(self):
        self.assertEqual(audience.decide(self.summary())["verdict"], "no leak across groups")
        self.assertEqual(audience.decide(self.summary(power_held=2))["verdict"],
                         "inconclusive (control 2 failed)")
        self.assertEqual(audience.decide(self.summary(determinism=False))["verdict"],
                         "inconclusive (control 1 failed)")
        self.assertEqual(audience.decide(self.summary(no_hidden_failed=["q9"]))["verdict"],
                         "leak (rules 4 failed, first failing question q9)")


# Rankings of the lexical workload on this suite, recorded with the script at
# commit f74a30c (before ``--embedder`` existed). The default run must not move.
G1, G2 = "2025-01-01|Group 1|", "2025-01-01|Group 2|"
DEFAULT_RANKINGS = {
    "q1": {
        "full": ([G2 + "1", G2 + "2", G2 + "3"],
                 [1.077076389544754, 0.6468739018714538, 0.14314186629740022]),
        "power": ([G1 + "1", G1 + "2", G2 + "1", G2 + "2", G1 + "3", G2 + "3"],
                  [1.1442339675608881, 1.0732712226088132, 0.9991886877825004,
                   0.6293133517698766, 0.26786308261307784, 0.14155421067086293]),
    },
    "q2": {
        "full": ([G2 + "2", G2 + "1", G2 + "3"],
                 [1.0658655072260546, 0.575693696673363, 0.29250000000000004]),
        "power": ([G2 + "2", G2 + "1", G1 + "3", G2 + "3", G1 + "1", G1 + "2"],
                  [1.0649938203199745, 0.570159176634759, 0.3615286943722391,
                   0.29250000000000004, 0.24880508714098723, 0.14593800893741296]),
    },
}


def rankings(embedder=None):
    data = suite()
    members = audience.memberships(data)
    full, full_ids = audience.build_store(data, power_viewer=True, embedder=embedder)
    out = {}
    try:
        for query in data["queries"]:
            asker = audience.choose_asker(query, members, audience.SEED)
            if asker is None:
                continue
            visible, visible_ids = audience.build_store(
                data, channels=frozenset(members[asker]), embedder=embedder)
            with visible:
                out[query["id"]] = {
                    "full": audience.ranked(full, full_ids, query["query"], [asker]),
                    "visible": audience.ranked(visible, visible_ids, query["query"], [asker]),
                    "power": audience.ranked(full, full_ids, query["query"],
                                             [audience.POWER_VIEWER]),
                    "leak": audience.ranked(full, full_ids, query["query"], None),
                }
    finally:
        full.close()
    return out


class DefaultConfigurationTests(unittest.TestCase):
    def test_the_default_workload_is_unchanged(self):
        store, _ = audience.build_store(suite())
        with store:
            self.assertIsNone(store.embedder)
        observed = rankings()
        self.assertEqual(sorted(observed), ["q1", "q2"])
        for question, expected in DEFAULT_RANKINGS.items():
            got = observed[question]
            for world, name in (("full", "full"), ("visible", "full"),
                                ("power", "power"), ("leak", "power")):
                keys, scores = expected[name]
                self.assertEqual(got[world][0], keys, (question, world))
                for left, right in zip(got[world][1], scores):
                    self.assertAlmostEqual(left, right, places=12, msg=(question, world))
        self.assertEqual(audience.run_suite(suite()), audience.run_suite(suite(), embedder=None))

    def test_the_default_report_says_lexical_and_records_no_embedder(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "smoke"
            with contextlib.redirect_stdout(io.StringIO()):
                audience.main(["--smoke", "--output", str(output)], loader=lambda topic: suite())
            report = json.loads(output.with_suffix(".json").read_text())
        self.assertIsNone(report["embedder"])
        self.assertIsNone(report["embedder_model"])
        self.assertIn("; lexical search, limit 10.", audience.render(report))


class NGramTests(unittest.TestCase):
    def test_the_vector_path_is_live(self):
        # "launches" shares no whole word with any message, only character 3-grams.
        lexical = rankings()
        hybrid = rankings("ngram")
        self.assertNotEqual(lexical["q1"]["full"][1], hybrid["q1"]["full"][1])
        data = suite()
        for embedder, expect_hits in ((None, False), ("ngram", True)):
            store, ids = audience.build_store(data, power_viewer=True, embedder=embedder)
            with store:
                keys, _ = audience.ranked(store, ids, "launches", ["Cy"])
                if embedder:
                    self.assertEqual(store.embedder.name, "ngram-hash:n=3:d=512")
            self.assertEqual(bool(keys), expect_hits, embedder)
            self.assertTrue(all(key.startswith(G2) for key in keys), keys)

    def test_the_current_store_passes_with_hybrid_search(self):
        result = audience.run_suite(suite(), embedder="ngram")
        self.assertEqual([row["id"] for row in result["rows"]], ["q1", "q2"])
        for row in result["rows"]:
            self.assertTrue(row["noninterference"] and row["no_hidden"] and row["power"], row)
        summary = audience.summarise(
            [result], audience.check_determinism(suite(), None, None, "ngram"))
        self.assertEqual(audience.decide(summary)["verdict"], "no leak across groups")

    def test_searching_without_viewers_fails_rules_3_and_4_with_hybrid_search(self):
        result = audience.run_suite(suite(), fault="leak", embedder="ngram")
        summary = audience.summarise([result], True)
        self.assertEqual(len(summary["noninterference_failed"]), 2)
        self.assertEqual(len(summary["no_hidden_failed"]), 2)
        self.assertTrue(audience.validate_fault(summary)["detected"])
        self.assertTrue(audience.decide(summary)["verdict"].startswith("leak (rules 3, 4 failed"))

    def test_a_vector_candidate_cut_before_the_audience_filter_fails_rule_3_only(self):
        # A plausible vector-index bug: take the top 2 cosine matches over the
        # whole store, then drop hidden ones. No hidden message is shown, but
        # hidden memories decide which visible ones get a vector rank.
        original = MemoryStore._vector_scores

        class Everything:
            def __contains__(self, item):
                return True

        def top_k_first(store, connection, memories, query_vector, viewers=None):
            every = original(store, connection, Everything(), query_vector, None)
            top = sorted(every, key=lambda memory_id: (every[memory_id], memory_id),
                         reverse=True)[:2]
            return {memory_id: every[memory_id] for memory_id in top if memory_id in memories}

        with mock.patch.object(MemoryStore, "_vector_scores", top_k_first):
            result = audience.run_suite(suite(), embedder="ngram")
        summary = audience.summarise([result], True)
        self.assertEqual(summary["noninterference_failed"], ["q1"])
        self.assertEqual(summary["no_hidden_failed"], [])
        q1 = result["rows"][0]
        self.assertEqual(q1["full"], q1["visible"])  # caught by the score check alone

    def test_a_hybrid_run_is_a_function_of_its_inputs(self):
        self.assertEqual(audience.run_suite(suite(), embedder="ngram"),
                         audience.run_suite(suite(), embedder="ngram"))
        self.assertEqual(audience.run_suite(suite(), fault="leak", embedder="ngram"),
                         audience.run_suite(suite(), fault="leak", embedder="ngram"))
        self.assertTrue(audience.check_determinism(suite(), None, None, "ngram"))
        self.assertEqual(rankings("ngram"), rankings("ngram"))

    def test_main_records_the_embedder(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "smoke"
            with contextlib.redirect_stdout(io.StringIO()):
                code = audience.main(["--smoke", "--embedder", "ngram", "--output", str(output)],
                                     loader=lambda topic: suite())
            report = json.loads(output.with_suffix(".json").read_text())
            text = output.with_suffix(".md").read_text()
        self.assertEqual(code, 0)
        self.assertEqual(report["embedder"], "ngram")
        self.assertEqual(report["embedder_model"], "ngram-hash:n=3:d=512")
        self.assertIn("hybrid search (lexical + NGramHashEmbedder", text)
        self.assertIn("`ngram-hash:n=3:d=512`), limit 10.", text)
        with self.assertRaises(ValueError):
            audience.make_embedder("minilm")


class MainTests(unittest.TestCase):
    def test_main_writes_a_marked_smoke_report_and_refuses_results_dir(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "smoke"
            with contextlib.redirect_stdout(io.StringIO()):
                code = audience.main(["--smoke", "--output", str(output)],
                                     loader=lambda topic: suite())
            report = json.loads(output.with_suffix(".json").read_text())
        self.assertEqual(code, 0)
        self.assertTrue(report["smoke"])
        self.assertIn("SMOKE RUN", audience.render(report))
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            audience.main(["--smoke", "--output", str(audience.RESULTS / "x")],
                          loader=lambda topic: suite())


if __name__ == "__main__":
    unittest.main()
