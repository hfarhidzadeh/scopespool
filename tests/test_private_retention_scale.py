import contextlib
import copy
import importlib.util
import io
import sys
import tempfile
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

    def test_the_default_run_is_the_recorded_workload_without_an_embedder(self):
        args = scale.parse_args([])
        self.assertEqual((args.sizes, args.repetitions, args.embedder, args.src),
                         (scale.SIZES, scale.REPETITIONS, None, None))
        self.assertEqual(scale.build_config(args.sizes, args.repetitions, args.embedder), {
            "sizes": [{"memories": 256, "readers": 2}, {"memories": 1024, "readers": 4},
                      {"memories": 4096, "readers": 8}],
            "repetitions": 4, "topics": 32, "search_limit": 5, "warmup": 4, "serial": 24,
            "mixed_before": 6, "mixed_after": 3, "previews_per_phase": 2,
            "retained_list_samples": 12, "retained_list_limit": 185, "journal_mode": "wal",
            "provisional_budgets": scale.BUDGETS, "embedder": None,
        })

    def test_partial_runs_choose_from_the_fixed_sizes(self):
        smoke = scale.parse_args(["--smoke", "--embedder", "ngram"])
        self.assertEqual((smoke.sizes, smoke.repetitions, smoke.embedder),
                         (((256, 2),), 1, "ngram"))
        one = scale.parse_args(["--size", "4096", "--repetitions", "1"])
        self.assertEqual((one.sizes, one.repetitions), (((4096, 8),), 1))
        both = scale.parse_args(["--size", "4096", "--size", "256"])
        self.assertEqual((both.sizes, both.repetitions), (((256, 2), (4096, 8)), 4))
        for bad in (["--size", "2048"], ["--repetitions", "0"], ["--smoke", "--size", "256"],
                    ["--smoke", "--repetitions", "2"], ["--embedder", "minilm"]):
            with self.subTest(bad=bad), self.assertRaises(SystemExit), \
                    contextlib.redirect_stderr(io.StringIO()):
                scale.parse_args(bad)

    def test_the_ngram_option_gives_the_store_an_embedder(self):
        self.assertIsNone(scale.make_embedder(None))
        self.assertEqual(type(scale.make_embedder("ngram")).__name__, "NGramHashEmbedder")
        with self.assertRaises(ValueError):
            scale.make_embedder("minilm")

    def test_an_alternate_source_must_be_the_one_imported(self):
        loaded = scale.store_source()
        self.assertEqual(loaded.name, "store.py")
        self.assertEqual(scale.store_source(loaded.parents[1]), loaded)
        with tempfile.TemporaryDirectory() as directory, self.assertRaises(ValueError):
            scale.store_source(Path(directory))

    def test_the_report_names_the_run_not_the_pilot(self):
        self.assertNotIn("pilot", scale.TITLE.lower())
        config = scale.build_config(((4096, 8),), 1, "ngram")
        line = scale.describe_run(config, "/elsewhere/src")
        self.assertIn("Embedder: ngram (NGramHashEmbedder", line)
        self.assertIn("4,096 memories / 8 readers; 1 paired repetition each.", line)
        self.assertIn("alternate source tree", line)
        self.assertIn("Embedder: none", scale.describe_run(scale.build_config(scale.SIZES, 4)))


class PruneSummaryOptionTests(unittest.TestCase):
    def test_the_option_is_off_by_default_and_the_default_config_keeps_its_shape(self):
        self.assertFalse(scale.parse_args([]).prune_summaries)
        self.assertFalse(scale.parse_args(["--smoke"]).prune_summaries)
        self.assertTrue(scale.parse_args(["--smoke", "--prune-summaries"]).prune_summaries)
        default = scale.build_config(scale.SIZES, 4)
        self.assertEqual(scale.build_config(scale.SIZES, 4, None, False), default)
        self.assertNotIn("prune_previews", default)
        self.assertNotIn("prune", scale.describe_run(default).lower())
        summaries = scale.build_config(scale.SIZES, 4, None, True)
        self.assertEqual(summaries, dict(default, prune_previews="summaries (details=False)"))
        self.assertIn("`--prune-summaries`", scale.describe_run(summaries))

    def test_only_the_option_adds_details_false_to_the_concurrent_previews(self):
        class Reader:
            def search(self, query, **options):
                return []

        class Store:
            def __init__(self):
                self.calls = []

            def prune(self, **options):
                self.calls.append(options)
                return []

        for summaries, expected in ((False, {"as_of": scale.NOW}),
                                    (True, {"as_of": scale.NOW, "details": False})):
            store = Store()
            arguments = (store, [Reader(), Reader()], [["topic1"], ["topic2"]], False)
            if summaries:
                scale.mixed_calls(*arguments, prune_summaries=True)
            else:
                scale.mixed_calls(*arguments)
            self.assertEqual(store.calls, [expected] * scale.PREVIEWS, summaries)

    def test_an_arm_previews_summaries_only_with_the_option(self):
        from dynmemory.store import PruneCandidate, PruneSummary

        with tempfile.TemporaryDirectory() as raw:
            template = Path(raw) / "template.db"
            scale.seed_database(template, 40, 2)
            previews = {}
            for summaries in (False, True):
                path = Path(raw) / "arm{}.db".format(int(summaries))
                scale.copy_database(template, path)
                options = {"prune_summaries": True} if summaries else {}
                _, checks, comparable = scale.arm(path, 2, True, 0, **options)
                previews[summaries] = comparable[1]
                self.assertTrue(checks["retention_matches_reader_accesses"])
                applied = comparable[2]
                self.assertTrue(applied)
                self.assertTrue(all(isinstance(item, PruneCandidate) for item in applied))
        for summaries, kind in ((False, PruneCandidate), (True, PruneSummary)):
            items = [item for preview in previews[summaries] for item in preview]
            self.assertTrue(items)
            self.assertTrue(all(isinstance(item, kind) for item in items), summaries)
        self.assertEqual(
            [[c.memory.id for c in preview] for preview in previews[False]],
            [[s.memory_id for s in preview] for preview in previews[True]],
        )


if __name__ == "__main__":
    unittest.main()
