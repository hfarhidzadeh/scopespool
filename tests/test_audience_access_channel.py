import contextlib
import importlib.util
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "experiments" / "audience_access_channel.py"
spec = importlib.util.spec_from_file_location("audience_access_channel_experiment", SCRIPT)
ac = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = ac
spec.loader.exec_module(ac)


def summary(trials, failed, right=None, optin=0):
    rates = {name: trials for name in ("detected_counters", "detected_prune", "right_counters",
                                       "right_prune", "exact", "time_visible")}
    rates["optin_right_counters"] = optin
    if right is not None:
        rates["right_counters"] = right
    return {
        "checks": {name: {"held": trials - len(failed.get(name, ())),
                          "not_held_seeds": sorted(failed.get(name, ()))} for name in ac.CHECKS},
        "rates": rates,
    }


def verdict(trials=10, right=None, optin=0, **failed):
    return ac.decide(summary(trials, failed, right, optin), trials)["verdict"]


class DecisionRuleTests(unittest.TestCase):
    def test_no_trace_when_every_rule_holds(self):
        self.assertEqual(verdict(), "reads leave no trace")

    def test_no_trace_by_default_but_opt_in_still_leaves_one(self):
        self.assertEqual(
            verdict(optin=10),
            "reads leave no trace by default; opting in still does (topic named from counters "
            "in 10 of 10 trials)")

    def test_a_trace_is_reported_with_the_guess_accuracy(self):
        self.assertEqual(
            verdict(trace=range(10), right=9),
            "reads leave a trace other members can see (topic named from counters in 9 of 10 "
            "trials; chance 12.5%)")

    def test_a_failed_control_is_inconclusive(self):
        self.assertEqual(verdict(determinism=[1]), "inconclusive (control 1 failed)")
        self.assertEqual(verdict(observer=[2], trace=[3]), "inconclusive (control 2 failed)")

    def test_a_failed_guarantee_beats_the_trace_reading(self):
        self.assertEqual(
            verdict(hidden=[7, 3], trace=[1]),
            "a read changes what others can observe beyond the memories it returned "
            "(rules 4 failed, first failing seed 3)")
        self.assertIn("rules 3, 4 failed", verdict(ranking=[5], hidden=[6]))


class HelperTests(unittest.TestCase):
    def test_wilson_interval_contains_the_rate_and_stays_in_range(self):
        low, high = ac.wilson(9, 10)
        self.assertTrue(0 < low < 0.9 < high <= 1)
        self.assertEqual(ac.wilson(0, 0), (0.0, 0.0))

    def test_a_guess_needs_overlap_and_breaks_ties_with_the_generator(self):
        import random
        team = {0: ["a", "b"], 1: ["c", "d"]}
        self.assertEqual(ac.guess(set(), team, random.Random(0)), (None, 0))
        self.assertEqual(ac.guess({"a"}, team, random.Random(0)), (0, 1))
        topic, ties = ac.guess({"a", "c"}, team, random.Random(0))
        self.assertEqual(ties, 2)
        self.assertIn(topic, (0, 1))


class TrialTests(unittest.TestCase):
    def test_a_trial_is_a_function_of_its_seed(self):
        self.assertEqual(ac.make_trial(4), ac.make_trial(4))
        self.assertEqual(ac.run_trial(4), ac.run_trial(4))
        json.dumps(ac.run_trial(4))

    def test_the_current_store_is_silent_by_default_and_leaves_a_trace_only_when_asked(self):
        for seed in range(6):
            result = ac.run_trial(seed)
            self.assertTrue(result["determinism"] and result["observer"], seed)
            self.assertTrue(result["ranking"] and result["hidden"], seed)
            self.assertTrue(result["trace"], seed)
            self.assertFalse(result["detected_counters"] or result["detected_prune"], seed)
            self.assertFalse(result["right_counters"] or result["right_prune"], seed)
            self.assertTrue(result["optin_right_counters"] and result["optin_right_prune"], seed)
            self.assertTrue(result["exact"] and result["time_visible"], seed)


class FaultTests(unittest.TestCase):
    def test_recording_outside_the_view_fails_the_hidden_rule(self):
        results = [ac.run_trial(seed, "record-foreign") for seed in range(6)]
        self.assertEqual([r["hidden"] for r in results], [False] * 6)
        self.assertTrue(all(r["observer"] and r["ranking"] for r in results))

    def test_a_popularity_boost_fails_the_ranking_rule(self):
        results = [ac.run_trial(seed, "popularity-boost") for seed in range(6)]
        self.assertEqual([r["ranking"] for r in results], [False] * 6)
        self.assertTrue(all(r["hidden"] for r in results))

    def test_an_unknown_fault_is_rejected(self):
        with self.assertRaises(ValueError):
            with ac.fault("unknown"):
                pass

    def test_validation_reports_the_share(self):
        trials = [ac.run_trial(seed, "record-foreign") for seed in range(4)]
        check = ac.validate_fault("record-foreign", trials)
        self.assertTrue(check["detected"])
        self.assertEqual(check["rule"], 4)


class MainTests(unittest.TestCase):
    def test_main_writes_the_report(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "report"
            with contextlib.redirect_stdout(io.StringIO()) as printed:
                ac.main(["--trials", "2", "--output", str(output)])
            report = json.loads(output.with_suffix(".json").read_text())
            text = output.with_suffix(".md").read_text()
        self.assertEqual(report["trials"], 2)
        self.assertIn(report["decision"]["verdict"], text)
        self.assertEqual(printed.getvalue().strip(), text.strip())


if __name__ == "__main__":
    unittest.main()
