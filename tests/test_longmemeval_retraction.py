import contextlib
import importlib.util
import io
import json
import random
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "experiments" / "longmemeval_retraction.py"
spec = importlib.util.spec_from_file_location("longmemeval_retraction_experiment", SCRIPT)
lr = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = lr
spec.loader.exec_module(lr)

COMMON = "project plan weekend dinner garden music trip budget".split()


def fixture_questions(count=12):
    rng = random.Random("retraction-fixture")
    questions = []
    for number in range(count):
        sessions, ids, dates = [], [], []
        for session in range(6):
            turns = []
            for turn in range(4):
                unique = ["u{}x{}y{}z{}".format(number, session, turn, mark) for mark in "abc"]
                words = rng.sample(COMMON, 4)
                text = " ".join([unique[0], "I talked about the", unique[1]] + words
                                + ["yesterday", unique[2]])
                turns.append({"role": "user", "content": text,
                              "has_answer": session == 1 and turn == 0})
                turns.append({"role": "assistant", "content": "ok", "has_answer": False})
            ids.append("s{}_{}".format(number, session))
            dates.append("2023/05/{:02d} (Sat) 10:00".format(session + 1))
            sessions.append(turns)
        sessions.append([{"role": "user", "content": "I went hiking last weekend with my brother today.",
                          "has_answer": False}])
        ids.append("shared_hike")
        dates.append("2023/05/09 (Tue) 10:00")
        questions.append({
            "question_id": "q{:02d}".format(number),
            "question": "What did I plan for the {}?".format(COMMON[number % 8]),
            "answer": "blue", "question_type": "single-session-user",
            "question_date": "2023/06/01 (Thu) 10:00",
            "haystack_session_ids": ids, "haystack_dates": dates, "haystack_sessions": sessions,
        })
    return questions


def setUpModule():
    lr.stageb.install_clock()
    lr.PARSED = lr.stageb.parse_questions(fixture_questions())
    lr.ELIGIBLE = sorted(lr.PARSED)


def tearDownModule():
    lr.stageb.restore_clock()
    lr.PARSED, lr.ELIGIBLE = {}, []


def summary(trials, failed):
    return {"checks": {name: {"held": trials - len(failed.get(name, ())),
                              "not_held_seeds": sorted(failed.get(name, ()))} for name in lr.CHECKS}}


def verdict(trials=10, **failed):
    return lr.decide(summary(trials, failed), trials)["verdict"]


class DecisionRuleTests(unittest.TestCase):
    def test_all_rules_holding_means_retraction_erases(self):
        self.assertEqual(verdict(), "retraction erases on real text")

    def test_a_failed_control_is_inconclusive(self):
        self.assertEqual(verdict(determinism=[2]), "inconclusive (control 1 failed)")
        self.assertEqual(verdict(probe=[4], erasure=[1]), "inconclusive (control 2 failed)")

    def test_failures_name_the_rules_and_first_seed(self):
        self.assertEqual(verdict(erasure=[7, 3]),
                         "retraction does not erase (rules 4 failed, first failing seed 3)")
        self.assertEqual(verdict(backup=[9], reads=[5]),
                         "retraction does not erase (rules 5, 7 failed, first failing seed 5)")


class TextTests(unittest.TestCase):
    def test_shingles_are_case_and_punctuation_blind(self):
        self.assertEqual(lr.shingles("Hello, World! one two three four"),
                         {"hello world one two three four"})
        self.assertEqual(lr.shingles("too short"), set())

    def test_a_shingle_matches_whole_tokens_only(self):
        corpus = lr.corpus_of(["it in the form of an announcement today"])
        self.assertEqual(lr.found_in(corpus, {"it in the form of a"}), 0)
        self.assertEqual(lr.found_in(corpus, {"it in the form of an"}), 1)
        self.assertEqual(lr.found_in(lr.corpus_of(["x y z it in the form of a"]),
                                     {"it in the form of a"}), 1)

    def test_the_corpus_keeps_values_apart(self):
        corpus = lr.corpus_of(["a b c d e", "f g h i j k"])
        self.assertEqual(lr.found_in(corpus, {"b c d e f g"}), 0)
        self.assertEqual(lr.found_in(corpus, {"f g h i j k"}), 1)


class TrialTests(unittest.TestCase):
    def test_a_trial_is_a_function_of_its_seed(self):
        self.assertEqual(lr.make_trial(5), lr.make_trial(5))
        self.assertEqual(lr.run_trial(5), lr.run_trial(5))
        json.dumps(lr.run_trial(5))

    def test_plans_are_well_formed(self):
        for seed in range(30):
            trial = lr.make_trial(seed)
            covered = sorted(i for m in trial["memories"] for i in m["sources"])
            self.assertEqual(covered, list(range(len(trial["texts"]))))
            for number in trial["retract"]:
                self.assertGreaterEqual(len(trial["distinct"][number]), lr.MIN_DISTINCT)
            self.assertEqual(bool(trial["links"]), trial["linked"] and len(trial["memories"]) > 1)
            self.assertEqual(trial["hybrid"], seed % 4 == 3)
            for memory in trial["memories"]:
                self.assertEqual({trial["speakers"][i] for i in memory["sources"]}, {memory["speaker"]})

    def test_distinctive_shingles_occur_in_one_message_only(self):
        trial = lr.make_trial(2)
        for number in trial["retract"]:
            for shingle in trial["distinct"][number]:
                holders = [i for i, text in enumerate(trial["texts"]) if shingle in lr.shingles(text)]
                self.assertEqual(holders, [number])

    def test_the_current_store_passes_in_every_family(self):
        for seed in range(8):  # plain, linked, hybrid and both
            result = lr.run_trial(seed)
            for name in lr.CHECKS:
                self.assertTrue(result[name], (seed, name))
            if not result["linked"]:
                self.assertEqual(result["classes"]["different"], 0, seed)
            self.assertEqual(result["copies"]["surviving"], result["copies"]["added"])


    def test_a_rebuilt_memory_does_not_inherit_the_links_of_the_one_it_replaces(self):
        # Found by this experiment: reads after a rebuild can rank differently from a
        # store that never got the message, in linked trials only, because the rebuilt
        # memory has no links. Reported, outside the verdict (see the script docstring).
        linked = [lr.run_trial(seed) for seed in (1, 3, 5, 7, 9, 11)]
        self.assertTrue(all(r["reads"] for r in linked))
        self.assertTrue(any(r["classes"]["different"] for r in linked if r["opportunities"]))


class FaultTests(unittest.TestCase):
    def results(self, flaw, count=8):
        return [lr.run_trial(seed, flaw) for seed in range(count)]

    def test_keeping_the_derived_text_fails_erasure(self):
        results = self.results("keep-text")
        self.assertTrue(all(r["probe"] for r in results))
        self.assertEqual([r["erasure"] for r in results], [False] * len(results))

    def test_keeping_pads_fails_only_the_backup_rule(self):
        results = self.results("keep-pads")
        self.assertEqual([r["backup"] for r in results], [False] * len(results))
        self.assertTrue(all(r["erasure"] and r["rebuild"] for r in results))

    def test_a_leaky_consolidator_fails_rebuild_where_it_can_run(self):
        results = [r for r in self.results("leaky-rebuild", 16) if r["opportunities"]]
        self.assertTrue(results)
        self.assertTrue(all(not r["rebuild"] for r in results))
        self.assertTrue(all(r["backup"] for r in results))

    def test_skipping_the_rebuild_fails_reads_where_a_memory_could_be_rebuilt(self):
        results = [r for r in self.results("no-rebuild", 16) if r["opportunities"] and not r["linked"]]
        self.assertTrue(results)
        self.assertTrue(all(not r["reads"] for r in results))

    def test_validation_reports_the_share(self):
        trials = self.results("keep-text", 4)
        check = lr.validate_fault("keep-text", trials)
        self.assertTrue(check["detected"])
        self.assertEqual(check["rule"], 4)


class MainTests(unittest.TestCase):
    def tearDown(self):
        lr.stageb.install_clock()  # main restores the real clock when it finishes

    def test_main_writes_the_report(self):
        with tempfile.TemporaryDirectory() as directory:
            data = Path(directory) / "data.json"
            data.write_text(json.dumps(fixture_questions()))
            output = Path(directory) / "report"
            with contextlib.redirect_stdout(io.StringIO()) as printed:
                lr.main(["--data", str(data), "--trials", "2", "--output", str(output)])
            report = json.loads(output.with_suffix(".json").read_text())
            text = output.with_suffix(".md").read_text()
        self.assertEqual(report["trials"], 2)
        self.assertIn(report["decision"]["verdict"], text)
        self.assertEqual(printed.getvalue().strip(), text.strip())


if __name__ == "__main__":
    unittest.main()
