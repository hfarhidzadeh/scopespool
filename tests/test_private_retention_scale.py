import copy
import importlib.util
import sys
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "experiments" / "private_retention_scale.py"
spec = importlib.util.spec_from_file_location("private_retention_scale", SCRIPT)
scale = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = scale
spec.loader.exec_module(scale)

ARM_CHECKS = {
    "observer_rankings_unchanged_by_reads": True,
    "retention_matches_reader_accesses": True,
    "shared_access_counters_unmodified": True,
    "private_storage_accounting": True,
    "expiry_and_cleanup": True,
}


def pair(memories=256, readers=2, repeat=1):
    return {
        "memories": memories, "readers": readers, "repeat": repeat,
        "all_calls_completed": True,
        "paired_comparison": {"all_successful_pairs_equal": True, "compared_attempts": 40,
                              "unpaired_attempts": 0},
        "checks": {"silent": dict(ARM_CHECKS), "private": dict(ARM_CHECKS)},
        "measurements": {"silent": {"personal_results_by_reader": [0] * readers},
                         "private": {"personal_results_by_reader": [3] * readers}},
    }


def pairs():
    return [pair(256, 2, 1), pair(256, 2, 2), pair(4096, 8, 1), pair(4096, 8, 2)]


class GateTests(unittest.TestCase):
    def test_every_criterion_holding_passes(self):
        gate = scale.acceptance_gate(pairs())
        self.assertEqual((gate["verdict"], gate["passed"], gate["first_failure"]), ("pass", True, None))
        self.assertEqual({item["held"] for item in gate["criteria"].values()}, {4})

    def test_a_lock_error_fails_criterion_a(self):
        runs = pairs()
        runs[2]["all_calls_completed"] = False
        gate = scale.acceptance_gate(runs)
        self.assertFalse(gate["passed"])
        self.assertEqual(gate["verdict"], "fail (a failed; first failing: 4,096 memories, pair 1)")
        self.assertEqual(gate["criteria"]["a_no_lock_errors"]["failing"],
                         [{"memories": 4096, "readers": 8, "pair": 1}])

    def test_an_unpaired_attempt_alone_fails_criterion_a(self):
        runs = pairs()
        runs[3]["paired_comparison"]["unpaired_attempts"] = 1
        self.assertIn("a failed", scale.acceptance_gate(runs)["verdict"])

    def test_a_mismatch_fails_criterion_b(self):
        for change in ("comparison", "observer"):
            runs = pairs()
            if change == "comparison":
                runs[1]["paired_comparison"]["all_successful_pairs_equal"] = False
            else:
                runs[1]["checks"]["silent"]["observer_rankings_unchanged_by_reads"] = False
            gate = scale.acceptance_gate(runs)
            self.assertEqual(gate["verdict"], "fail (b failed; first failing: 256 memories, pair 2)",
                             change)

    def test_a_reader_with_no_retained_entry_fails_criterion_c(self):
        runs = pairs()
        runs[2]["measurements"]["private"]["personal_results_by_reader"][5] = 0
        gate = scale.acceptance_gate(runs)
        self.assertEqual(gate["verdict"], "fail (c failed; first failing: 4,096 memories, pair 1)")
        runs = pairs()
        runs[0]["checks"]["private"]["retention_matches_reader_accesses"] = False
        self.assertIn("c failed", scale.acceptance_gate(runs)["verdict"])

    def test_a_missing_or_short_reader_list_fails_criterion_c(self):
        runs = pairs()
        del runs[0]["measurements"]["private"]["personal_results_by_reader"]
        self.assertIn("c failed", scale.acceptance_gate(runs)["verdict"])
        runs = pairs()
        runs[0]["measurements"]["private"]["personal_results_by_reader"] = [3]
        self.assertIn("c failed", scale.acceptance_gate(runs)["verdict"])

    def test_several_failures_are_all_named_and_the_first_pair_is_reported(self):
        runs = pairs()
        runs[3]["all_calls_completed"] = False
        runs[1]["paired_comparison"]["all_successful_pairs_equal"] = False
        gate = scale.acceptance_gate(runs)
        self.assertEqual(gate["verdict"], "fail (a, b failed; first failing: 256 memories, pair 2)")
        self.assertEqual(gate["first_failure"]["criteria"], ["b_results_match"])

    def test_no_pairs_is_not_a_pass(self):
        self.assertEqual(scale.acceptance_gate([])["verdict"], "fail (no pairs ran)")

    def test_the_gate_reads_but_does_not_change_the_pairs(self):
        runs = pairs()
        before = copy.deepcopy(runs)
        scale.acceptance_gate(runs)
        self.assertEqual(runs, before)


class WorkloadTests(unittest.TestCase):
    def test_the_workload_is_unchanged_from_the_pilot(self):
        self.assertEqual(scale.SIZES, ((256, 2), (1024, 4), (4096, 8)))
        self.assertEqual((scale.REPETITIONS, scale.TOPICS, scale.LIMIT, scale.WARMUP, scale.SERIAL,
                          scale.MIXED_BEFORE, scale.MIXED_AFTER, scale.PREVIEWS, scale.LIST_SAMPLES),
                         (4, 32, 5, 4, 24, 6, 3, 2, 12))

    def test_the_gate_is_written_in_the_docstring(self):
        for name in ("(a)", "(b)", "(c)", "personal_results_by_reader", "unpaired_attempts"):
            self.assertIn(name, scale.__doc__)


if __name__ == "__main__":
    unittest.main()
