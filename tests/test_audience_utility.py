import hashlib
import importlib.util
import io
import json
import math
import random
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPT = Path(__file__).resolve().parents[1] / "experiments" / "audience_utility.py"
spec = importlib.util.spec_from_file_location("audience_utility_experiment", SCRIPT)
utility = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = utility
spec.loader.exec_module(utility)

SEED = 1
ARMS = utility.ARMS
ORIGINAL_SEARCH = utility.MemoryStore.search
CONTENT = re.compile(r"^The (\w+) of (\w+) is (\w+)\.((?: \w+)*)$")


def summary(pooled=0.9, owner=1.0, missing=0, leaks=None, ci=(0.0, 0.0), mean=0.0):
    """A synthetic summary holding the fields ``decide`` reads (1,000 items each)."""
    counts = dict({"after-k": 0, "after-all": 0, "built": 0}, **(leaks or {}))
    counts["pooled"] = round(pooled * 1000)
    return {
        "leakage": {
            "items": 1000,
            "by_arm": {
                arm: {"leaks": count, "first_seed": 7 if count else None}
                for arm, count in counts.items()
            },
        },
        "owner": {"items": 1000, "by_arm": {"built": {"hits": round(owner * 1000)}}},
        "over_blocking": {"items": 1000, "missing": missing},
        "utility": {
            "differences": {"built_minus_after_all": {"mean": mean, "ci95": list(ci)}}
        },
    }


def decision(**options):
    return utility.decide(summary(**options), 200)


def scores(rr=None, leaks=None, owner_hits=15, returned=30):
    """Per-trial scores as ``score_items`` returns them."""
    return {
        "utility": {
            "items": 120,
            "rr": dict({"pooled": 0.9, "after-k": 1.0, "after-all": 1.0, "built": 1.0}, **(rr or {})),
            "hit": {arm: 1.0 for arm in ARMS},
            "shown": {arm: 10.0 for arm in ARMS},
        },
        "leakage": {
            "items": 50,
            "leaks": dict({"pooled": 40, "after-k": 0, "after-all": 0, "built": 0}, **(leaks or {})),
        },
        "owner": {"items": 15, "hits": {arm: owner_hits for arm in ARMS}},
        "over_blocking": {"items": 30, "returned": returned, "hit_at_k": returned},
    }


def trial(seed, **options):
    return {
        "seed": seed,
        "members": {},
        "memories": 150,
        "timestamps_increase": True,
        "items": [],
        "scores": scores(**options),
    }


def search_ignoring_viewers(self, query, **options):
    """A broken store: reads with viewers see everything."""
    options.pop("viewers", None)
    return ORIGINAL_SEARCH(self, query, **options)


def search_hiding_everything(self, query, **options):
    """A broken store: reads with viewers see nothing."""
    if options.get("viewers") is not None:
        return []
    return ORIGINAL_SEARCH(self, query, **options)


def run_subset(seed, search):
    """Ask one viewer's utility items and every canary item, against a patched store."""
    workspace = utility.build_workspace(seed)
    asked = [
        item
        for item in utility.questions(workspace)
        if item["type"] != "utility" or item["viewer"] == utility.MEMBERS[0]
    ]
    with mock.patch.object(utility.MemoryStore, "search", search):
        with utility.MemoryStore(":memory:") as store:
            labels, _ = utility.populate(store, workspace)
            items = utility.answer(store, labels, workspace, asked)
    return dict(trial(seed), items=items, scores=utility.score_items(items))


class DecisionRuleTests(unittest.TestCase):
    def test_clean_filtered_arms_at_no_cost_support_h1(self):
        result = decision()
        self.assertEqual(result["verdict"], "H1 supported")
        self.assertTrue(result["rule_1_positive_controls_hold"])
        self.assertTrue(result["rule_2_no_over_blocking"])
        self.assertTrue(result["rule_3_zero_leakage"])
        self.assertEqual(result["rule_4_utility"], "no utility cost")

    def test_a_pooled_arm_that_leaks_too_little_is_inconclusive(self):
        result = decision(pooled=0.49)
        self.assertFalse(result["rule_1_pooled_leaks"])
        self.assertEqual(result["verdict"], "inconclusive (a control failed)")
        self.assertEqual(decision(pooled=0.5)["verdict"], "H1 supported")

    def test_owners_who_miss_their_canaries_make_it_inconclusive(self):
        result = decision(owner=0.94)
        self.assertFalse(result["rule_1_owner_finds_canary"])
        self.assertEqual(result["verdict"], "inconclusive (a control failed)")
        self.assertEqual(decision(owner=0.95)["verdict"], "H1 supported")

    def test_one_over_blocked_item_makes_it_inconclusive(self):
        result = decision(missing=1)
        self.assertFalse(result["rule_2_no_over_blocking"])
        self.assertEqual(result["verdict"], "inconclusive (a control failed)")

    def test_a_failed_control_comes_before_a_leak(self):
        result = decision(missing=1, leaks={"built": 3})
        self.assertEqual(result["verdict"], "inconclusive (a control failed)")
        self.assertFalse(result["rule_3_zero_leakage"])

    def test_one_leak_in_any_filtered_arm_rejects_h1(self):
        for arm in utility.FILTERED_ARMS:
            result = decision(leaks={arm: 1})
            self.assertFalse(result["rule_3_zero_leakage"])
            self.assertFalse(result["rule_3_zero_leakage_by_arm"][arm])
            self.assertTrue(result["verdict"].startswith("H1 not supported: rule 3"), arm)
            self.assertIn("{} (1 of 1000 items, first failing seed 7)".format(arm), result["verdict"])

    def test_utility_readings_at_the_margin(self):
        cases = {
            (0.0, 0.0): "no utility cost",
            (-0.01, 0.02): "no utility cost",
            (-0.0100001, 0.02): "unclear",
            (-0.02, -0.01): "unclear",
            (-0.05, -0.0100001): "utility cost",
        }
        for ci, reading in cases.items():
            self.assertEqual(utility.utility_reading(list(ci)), reading, ci)

    def test_a_utility_cost_rejects_h1(self):
        result = decision(ci=(-0.05, -0.02), mean=-0.035)
        self.assertEqual(result["rule_4_utility"], "utility cost")
        self.assertEqual(
            result["verdict"],
            "H1 not supported: rule 4, utility cost "
            "(built minus after-all -0.0350, 95% CI -0.0500 to -0.0200)",
        )

    def test_an_unclear_utility_rejects_h1(self):
        result = decision(ci=(-0.03, 0.01), mean=-0.01)
        self.assertEqual(result["rule_4_utility"], "unclear")
        self.assertTrue(result["verdict"].startswith("H1 not supported: rule 4, utility unclear"))

    def test_every_reason_is_listed(self):
        result = decision(leaks={"built": 2}, ci=(-0.05, -0.02))
        self.assertEqual(len(result["reasons"]), 2)
        self.assertTrue(result["verdict"].startswith("H1 not supported: rule 3"))
        self.assertIn("; rule 4, utility cost", result["verdict"])


class SummaryTests(unittest.TestCase):
    def test_counts_and_first_failing_seeds(self):
        result = utility.summarise(
            [trial(4), trial(6, leaks={"built": 1}, returned=29), trial(5, leaks={"built": 2})]
        )
        built = result["leakage"]["by_arm"]["built"]
        self.assertEqual((built["leaks"], built["trials_with_leak"], built["first_seed"]), (3, 2, 5))
        self.assertEqual(result["leakage"]["items"], 150)
        self.assertEqual(result["leakage"]["by_arm"]["pooled"]["leaks"], 120)
        self.assertIsNone(result["leakage"]["by_arm"]["after-all"]["first_seed"])
        over = result["over_blocking"]
        self.assertEqual((over["missing"], over["first_seed"]), (1, 6))
        self.assertIsNone(result["owner"]["built_first_miss_seed"])

    def test_d_is_built_minus_after_all_per_trial(self):
        trials = [trial(seed, rr={"after-all": 0.75}) for seed in range(3)]
        difference = utility.summarise(trials)["utility"]["differences"]["built_minus_after_all"]
        self.assertEqual(difference["values"], [0.25, 0.25, 0.25])
        self.assertEqual(difference["mean"], 0.25)
        self.assertEqual(difference["ci95"], [0.25, 0.25])
        self.assertEqual((difference["higher"], difference["equal"], difference["lower"]), (3, 0, 0))

    def test_the_bootstrap_uses_random_0_and_the_51st_and_1950th_means(self):
        values = [0.0, 0.1, -0.2, 0.05, 0.3]
        rng = random.Random(0)
        means = sorted(
            sum(rng.choice(values) for _ in values) / len(values) for _ in range(2000)
        )
        result = utility.bootstrap(values)
        self.assertEqual(result["ci95"], [means[50], means[1949]])
        self.assertLess(result["ci95"][0], result["mean"])
        self.assertLess(result["mean"], result["ci95"][1])


class ScoringTests(unittest.TestCase):
    def test_reciprocal_rank_counts_the_first_gold_within_k(self):
        shown = ["x{}".format(index) for index in range(12)]
        self.assertEqual(utility.reciprocal_rank(shown, ["x2", "x5"]), 1 / 3)
        self.assertEqual(utility.reciprocal_rank(shown, ["x10"]), 0.0)
        self.assertEqual(utility.reciprocal_rank([], ["x0"]), 0.0)

    def test_items_are_scored_per_arm(self):
        shown = {"pooled": ["h", "g"], "after-k": ["g"], "after-all": ["g", "v"], "built": []}
        items = [
            {"type": "utility", "gold": ["g"], "shown": shown},
            {"type": "leakage", "canary": "h", "shown": shown},
            {"type": "owner", "canary": "g", "shown": shown},
            {
                "type": "over_blocking",
                "canary": "c",
                "shown": {"built": ["x{}".format(index) for index in range(11)] + ["c"]},
            },
        ]
        result = utility.score_items(items)
        self.assertEqual(
            result["utility"]["rr"], {"pooled": 0.5, "after-k": 1.0, "after-all": 1.0, "built": 0.0}
        )
        self.assertEqual(result["utility"]["shown"]["after-all"], 2.0)
        self.assertEqual(
            result["leakage"]["leaks"], {"pooled": 1, "after-k": 0, "after-all": 0, "built": 0}
        )
        self.assertEqual(result["owner"]["hits"]["built"], 0)
        self.assertEqual(result["over_blocking"], {"items": 1, "returned": 1, "hit_at_k": 0})


class DetectorTests(unittest.TestCase):
    """The checks fire when the store is broken on purpose."""

    def test_a_store_that_ignores_viewers_fails_rule_3(self):
        broken = run_subset(SEED, search_ignoring_viewers)
        leaks = broken["scores"]["leakage"]["leaks"]
        self.assertGreater(leaks["built"], 0)
        self.assertEqual((leaks["after-k"], leaks["after-all"]), (0, 0))
        result = utility.decide(utility.summarise([broken]), 1)
        self.assertEqual(result["rule_3_zero_leakage_by_arm"]["built"], False)
        self.assertTrue(result["verdict"].startswith("H1 not supported: rule 3, leaks in built"))

    def test_a_store_that_shows_viewers_nothing_fails_the_controls(self):
        broken = run_subset(SEED, search_hiding_everything)
        self.assertEqual(broken["scores"]["leakage"]["leaks"]["built"], 0)
        self.assertEqual(broken["scores"]["over_blocking"]["returned"], 0)
        self.assertEqual(broken["scores"]["owner"]["hits"]["built"], 0)
        result = utility.decide(utility.summarise([broken]), 1)
        self.assertFalse(result["rule_2_no_over_blocking"])
        self.assertEqual(result["verdict"], "inconclusive (a control failed)")


class TrialTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workspace = utility.build_workspace(SEED)
        cls.trial = utility.run_trial(SEED)
        cls.channels = utility.visible_channels(cls.workspace)
        cls.memory = {memory["label"]: memory for memory in cls.workspace["memories"]}

    def visible(self, viewer, label):
        return self.memory[label]["channel"] in self.channels[viewer]

    def items(self, kind):
        return [item for item in self.trial["items"] if item["type"] == kind]

    def test_the_workspace_follows_the_spec(self):
        members = self.workspace["members"]
        self.assertEqual(members["general"], list(utility.MEMBERS))
        for channel in utility.PRIVATE_CHANNELS:
            self.assertIn(len(members[channel]), (2, 3, 4))
            self.assertLessEqual(set(members[channel]), set(utility.MEMBERS))
        memories = self.workspace["memories"]
        self.assertEqual(len(memories), 150)
        for channel, facts in (("general", 40), ("p1", 30), ("p2", 30), ("p3", 30)):
            in_channel = [memory for memory in memories if memory["channel"] == channel]
            self.assertEqual(sum(not memory["canary"] for memory in in_channel), facts)
            self.assertEqual(sum(memory["canary"] for memory in in_channel), 5)
        self.assertEqual(
            {memory["value"] for memory in memories if memory["canary"]},
            {"canary{}x{}".format(SEED, k) for k in range(20)},
        )
        for memory in memories:
            self.assertIn(memory["speaker"], members[memory["channel"]])
            attribute, subject, value, filler = CONTENT.match(memory["content"]).groups()
            self.assertEqual(
                (attribute, subject, value), (memory["attribute"], memory["subject"], memory["value"])
            )
            self.assertIn(subject, utility.SUBJECTS)
            self.assertIn(attribute, utility.ATTRIBUTES)
            self.assertLessEqual(len(filler.split()), 6)
            self.assertLessEqual(set(filler.split()), set(utility.FILLER))
            if not memory["canary"]:
                self.assertIn(value, utility.VALUES)
        vocabularies = [
            set(utility.SUBJECTS),
            set(utility.ATTRIBUTES),
            set(utility.VALUES),
            set(utility.FILLER),
            {"the", "of", "is"},
        ]
        words = [word for vocabulary in vocabularies for word in vocabulary]
        self.assertEqual(len(words), len(set(words)))

    def test_the_store_holds_the_recorded_memberships(self):
        with utility.MemoryStore(":memory:") as store:
            labels, stamps = utility.populate(store, self.workspace)
            for member in utility.MEMBERS:
                self.assertEqual(store.channels_of(member), sorted(self.channels[member]))
            stored = store.list_memories(limit=1000)
        self.assertEqual(len(stored), 150)
        self.assertEqual({labels[memory.id] for memory in stored}, set(self.memory))
        self.assertEqual(stamps, sorted(stamps))

    def test_questions_follow_the_spec(self):
        utility_items = self.items("utility")
        for viewer in utility.MEMBERS:
            asked = [item for item in utility_items if item["viewer"] == viewer]
            self.assertEqual(len(asked), 20)
            self.assertEqual(len({item["query"] for item in asked}), 20)
            for item in asked:
                attribute, subject = item["query"].split()
                expected = sorted(
                    label
                    for label, memory in self.memory.items()
                    if (memory["subject"], memory["attribute"]) == (subject, attribute)
                    and self.visible(viewer, label)
                )
                self.assertTrue(expected)
                self.assertEqual(item["gold"], expected)
        canaries = [label for label, memory in self.memory.items() if memory["canary"]]
        private = [label for label in canaries if self.memory[label]["channel"] != "general"]
        self.assertEqual(
            sorted((item["viewer"], item["canary"]) for item in self.items("leakage")),
            sorted(
                (viewer, label)
                for viewer in utility.MEMBERS
                for label in private
                if not self.visible(viewer, label)
            ),
        )
        owners = self.items("owner")
        self.assertEqual(sorted(item["canary"] for item in owners), sorted(private))
        for item in owners:
            self.assertEqual(item["viewer"], self.memory[item["canary"]]["speaker"])
        self.assertEqual(len(self.items("over_blocking")), 5 * 6)
        for item in self.trial["items"]:
            if item["type"] != "utility":
                canary = self.memory[item["canary"]]
                self.assertEqual(item["query"], "{} {}".format(canary["attribute"], canary["subject"]))

    def test_each_arm_shows_what_it_should(self):
        for item in self.trial["items"]:
            viewer = item["viewer"]
            if item["type"] == "over_blocking":
                for label in item["shown"]["built"]:
                    self.assertTrue(self.visible(viewer, label), label)
                continue
            shown = item["shown"]
            for arm in ARMS:
                self.assertLessEqual(len(shown[arm]), utility.K)
            for arm in utility.FILTERED_ARMS:
                for label in shown[arm]:
                    self.assertTrue(self.visible(viewer, label), (arm, label))
            words = set(item["query"].split())
            matches = sum(
                bool(words & set(re.findall(r"\w+", memory["content"])))
                for memory in self.memory.values()
            )
            self.assertEqual(len(shown["pooled"]), min(utility.K, matches))
            # search(q, limit=k) is the first k of the full ranking, filtered.
            self.assertEqual(
                shown["after-k"],
                [label for label in shown["pooled"] if self.visible(viewer, label)],
            )

    def test_the_positive_controls_can_fire(self):
        scores = self.trial["scores"]
        self.assertGreater(scores["leakage"]["leaks"]["pooled"], 0)
        self.assertGreater(scores["owner"]["hits"]["built"], 0)
        self.assertTrue(self.trial["timestamps_increase"])
        self.assertEqual(self.trial["memories"], 150)

    def test_a_trial_is_reproducible(self):
        self.assertEqual(utility.run_trial(SEED), self.trial)

    def test_a_report_renders_and_serialises(self):
        report = utility.report_for([self.trial])
        json.dumps(report)
        text = utility.render(report)
        self.assertIn("**Verdict: {}**".format(report["decision"]["verdict"]), text)
        for arm in ARMS:
            self.assertIn(utility.ARM_LABELS[arm], text)


RESULTS = Path(__file__).resolve().parents[1] / "experiments" / "results"
# sha256 of json.dumps(run_trial(1), sort_keys=True), taken from the script at
# f74a30c before the hard workload was added.
DEFAULT_TRIAL_1_SHA256 = "946d71e03ceafb8677133ab7ed701be88ece077da9ce8e61d4db6616b09ff68f"
HARD_CONTENT = re.compile(
    r"^(?:(?P<alead>(?:\w+ )+)report: |(?P<slead>(?:\w+ )+)sync notes: )?"
    r"(?:The (?P<a>\w+) of (?P<s>\w+) is (?P<v>\w+)(?:; (?P<other>\w+) unaffected)?\."
    r"|Noted (?P<ms>\w+) and (?P<ma>\w+) in passing\.)(?P<filler>(?: \w+)*)$"
)


class DefaultWorkloadUnchangedTests(unittest.TestCase):
    """The hard mode leaves the default configuration and its report as they were."""

    def test_a_default_trial_is_byte_for_byte_what_it_was(self):
        digest = hashlib.sha256(
            json.dumps(utility.run_trial(1), sort_keys=True).encode()
        ).hexdigest()
        self.assertEqual(digest, DEFAULT_TRIAL_1_SHA256)

    def test_the_recorded_report_still_reads_and_renders_the_same(self):
        recorded = json.loads((RESULTS / "audience_utility.json").read_text())
        self.assertEqual(utility.report_for([utility.run_trial(0)])["settings"], recorded["settings"])
        self.assertEqual(
            json.loads(json.dumps(utility.decide(recorded["summary"], recorded["trials"]))),
            recorded["decision"],
        )
        self.assertEqual(
            utility.render(recorded), (RESULTS / "audience_utility.md").read_text()
        )

    def test_main_without_hard_writes_the_default_report(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "default"
            with mock.patch("sys.stdout", io.StringIO()):
                utility.main(["--trials", "1", "--output", str(output)])
            report = utility.report_for([utility.run_trial(0)])
            self.assertEqual(
                json.loads(output.with_suffix(".json").read_text()), json.loads(json.dumps(report))
            )
            self.assertEqual(output.with_suffix(".md").read_text(), utility.render(report))
            self.assertNotIn("mode", report)

    def test_fault_needs_hard(self):
        with mock.patch("sys.stderr", io.StringIO()), self.assertRaises(SystemExit):
            utility.main(["--fault", "fault-swap-top"])


def hard_summary(
    pooled=1.0, owner=1.0, missing=0, leaks=None, ceiling_trials=200, ceiling_items=400,
    after_all_below=400, readings=None, faults=("utility cost", "utility cost"), identical=True,
):
    """A synthetic hard summary holding the fields ``hard_decide`` reads."""
    counts = dict({"after-k": 0, "after-all": 0, "built": 0}, **(leaks or {}))
    counts["pooled"] = round(pooled * 1000)
    readings = dict({m: "no utility cost" for m in utility.H_METRICS}, **(readings or {}))
    ci = {"no utility cost": [-0.005, 0.005], "unclear": [-0.02, 0.0], "utility cost": [-0.05, -0.02]}

    def metrics(reading_of):
        return {
            m: {"reading": reading_of[m], "mean": sum(ci[reading_of[m]]) / 2, "ci95": ci[reading_of[m]]}
            for m in utility.H_METRICS
        }

    differences = {"built_minus_after_all": {"metrics": metrics(readings)}}
    for key, reading in zip(("drop_term_minus_after_all", "swap_top_minus_after_all"), faults):
        differences[key] = {"metrics": metrics({m: reading for m in utility.H_METRICS})}
    return {
        "trials": 200,
        "leakage": {
            "items": 1000,
            "by_arm": {
                arm: {"leaks": count, "first_seed": 7 if count else None} for arm, count in counts.items()
            },
        },
        "owner": {"items": 1000, "by_arm": {"built": {"hits": round(owner * 1000)}}},
        "over_blocking": {"items": 1000, "missing": missing},
        "ceiling": {"items": 1600, "items_below_one": ceiling_items, "trials_below_one": ceiling_trials},
        "utility": {"items": 2000, "after_all_ndcg_below_one": after_all_below, "differences": differences},
        "determinism": {"identical": identical},
    }


class HardDecisionRuleTests(unittest.TestCase):
    def verdict(self, **options):
        return utility.hard_decide(hard_summary(**options))

    def test_clean_controls_and_no_cost_support_h1(self):
        result = self.verdict()
        self.assertEqual(result["verdict"], "H1 supported")
        self.assertTrue(result["rule_3_below_ceiling"])
        self.assertTrue(result["rule_4_faults_detected"])

    def test_each_control_failure_is_inconclusive(self):
        failures = {
            "pooled": dict(pooled=0.49),
            "owner": dict(owner=0.94),
            "over-blocking": dict(missing=1),
            "ceiling trials": dict(ceiling_trials=189),
            "ceiling items": dict(ceiling_items=319),
            "after-all at the ceiling": dict(after_all_below=399),
            "drop-term fault missed": dict(faults=("unclear", "utility cost")),
            "swap-top fault missed": dict(faults=("utility cost", "no utility cost")),
            "nondeterministic": dict(identical=False),
        }
        for name, options in failures.items():
            self.assertEqual(self.verdict(**options)["verdict"], "inconclusive (a control failed)", name)
        # The thresholds themselves pass.
        for options in (dict(ceiling_trials=190), dict(ceiling_items=320), dict(after_all_below=400)):
            self.assertEqual(self.verdict(**options)["verdict"], "H1 supported", options)

    def test_a_cost_on_any_metric_or_a_leak_rejects_h1(self):
        for metric in utility.H_METRICS:
            for reading in ("utility cost", "unclear"):
                result = self.verdict(readings={metric: reading})
                self.assertTrue(result["verdict"].startswith("H1 not supported: rule 7"), (metric, reading))
                self.assertIn(utility.H_METRIC_LABELS[metric], result["verdict"])
        result = self.verdict(leaks={"built": 1})
        self.assertTrue(result["verdict"].startswith("H1 not supported: rule 6, leaks in built"))

    def test_difference_readings_and_sign_test(self):
        self.assertEqual(
            utility.difference_readings([-0.01, 0.01]),
            {"reading": "no utility cost", "equal_within_margin": True, "difference_detected": False},
        )
        self.assertEqual(
            utility.difference_readings([0.002, 0.02]),
            {"reading": "no utility cost", "equal_within_margin": False, "difference_detected": True},
        )
        self.assertEqual(utility.difference_readings([-0.05, -0.02])["reading"], "utility cost")
        self.assertEqual(utility.sign_test(0, 0), 1.0)
        self.assertAlmostEqual(utility.sign_test(0, 10), 2 / 1024)
        self.assertAlmostEqual(utility.sign_test(3, 3), 1.0)
        self.assertAlmostEqual(utility.sign_test(8, 2), 2 * (1 + 10 + 45) / 1024)


class HardMetricTests(unittest.TestCase):
    def test_ndcg(self):
        gold = {"a": 2, "b": 1}
        self.assertEqual(utility.ndcg_at_k(["a", "b", "x"], gold), 1.0)
        ideal = 3 + 1 / math.log2(3)
        self.assertAlmostEqual(utility.ndcg_at_k(["b", "a"], gold), (1 + 3 / math.log2(3)) / ideal)
        self.assertAlmostEqual(utility.ndcg_at_k(["x", "a"], gold), (3 / math.log2(3)) / ideal)
        self.assertEqual(utility.ndcg_at_k(["x"] * 3 + ["a"], {}), 0.0)
        beyond = ["x{}".format(i) for i in range(10)] + ["a"]
        self.assertEqual(utility.ndcg_at_k(beyond, gold), 0.0)

    def test_graded_rr_counts_grade_2_only(self):
        gold = {"m": 1, "a": 2}
        self.assertEqual(utility.graded_reciprocal_rank(["m", "x", "a"], gold), 1 / 3)
        self.assertEqual(utility.graded_reciprocal_rank(["m"], gold), 0.0)

    def test_recall_at_3_is_below_one_for_large_sets(self):
        gold = {label: 1 for label in "abcde"}
        self.assertEqual(utility.recall_at(["a", "b", "c", "d"], gold), 3 / 5)
        self.assertEqual(utility.recall_at(["x", "a"], {"a": 2}), 1.0)
        self.assertEqual(utility.recall_at(["x", "y", "z", "a"], {"a": 2}), 0.0)

    def test_drop_rarest_word(self):
        self.assertEqual(utility.drop_rarest_word("budget sub01", {"budget": 9, "sub01": 4}), "budget")
        self.assertEqual(utility.drop_rarest_word("budget sub01", {"budget": 4, "sub01": 4}), "sub01")


class HardTrialTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workspace = utility.hard_build_workspace(SEED)
        cls.trial = utility.hard_run_trial(SEED)
        cls.memory = {memory["label"]: memory for memory in cls.workspace["memories"]}

    def sees(self, audience, label):
        return utility.audience_sees(self.workspace, audience, self.memory[label]["channel"])

    def items(self, kind):
        return [item for item in self.trial["items"] if item["type"] == kind]

    def test_the_workspace_follows_the_spec(self):
        members = self.workspace["members"]
        self.assertEqual(members["general"], list(utility.MEMBERS))
        for channel in utility.PRIVATE_CHANNELS:
            self.assertIn(len(members[channel]), utility.H_PRIVATE_SIZES)
        focus = [tuple(pair) for pair in self.workspace["focus"]]
        self.assertEqual(len(set(focus)), 8)
        memories = self.workspace["memories"]
        self.assertEqual(len(self.memory), len(memories))
        for number, (s, a) in enumerate(focus):
            prefix = "f{}/".format(number)
            mine = [m for m in memories if m["label"].startswith(prefix)]
            forms = [m["label"][len(prefix):].rstrip("0123456789") for m in mine]
            self.assertIn(forms.count("answer"), range(3, 7))
            self.assertIn(forms.count("mention"), range(2, 5))
            self.assertEqual((forms.count("attribute"), forms.count("subject"), forms.count("decoy")), (3, 3, 2))
            for memory in mine:
                kind = memory["label"][len(prefix):].rstrip("0123456789")
                expected = 2 if kind == "answer" else 1 if kind == "mention" else 0
                self.assertEqual(utility.grade(memory, s, a), expected, memory["label"])
                words = set(memory["content"].replace(".", " ").replace(";", " ").replace(":", " ").split())
                self.assertTrue({s, a} & words, memory["label"])
                if kind == "decoy":
                    self.assertLessEqual({s, a}, words)
        canaries = [m for m in memories if m["canary"]]
        self.assertEqual(len(canaries), 12)
        self.assertEqual({m["value"] for m in canaries}, {"canary{}h{}".format(SEED, k) for k in range(12)})
        self.assertEqual(sum(m["label"].startswith("background") for m in memories), 40)
        for memory in memories:
            self.assertIn(memory["speaker"], members[memory["channel"]])
            match = HARD_CONTENT.match(memory["content"])
            self.assertIsNotNone(match, memory["content"])
            if match.group("ms"):
                self.assertEqual((match.group("ms"), match.group("ma")), (memory["subject"], memory["attribute"]))
                self.assertEqual(memory["form"], "mention")
            else:
                self.assertEqual(
                    (match.group("a"), match.group("s"), match.group("v")),
                    (memory["attribute"], memory["subject"], memory["value"]),
                )
            self.assertLessEqual(set(match.group("filler").split()), set(utility.FILLER))
        vocabularies = [
            set(utility.H_SUBJECTS), set(utility.H_ATTRIBUTES), set(utility.VALUES),
            set(utility.FILLER), set(utility.H_TEMPLATE_WORDS),
        ]
        words = [word for vocabulary in vocabularies for word in vocabulary]
        self.assertEqual(len(words), len(set(words)))

    def test_questions_follow_the_spec(self):
        audiences = sorted({tuple(item["audience"]) for item in self.items("utility")}, key=len)
        self.assertTrue({len(audience) for audience in audiences} >= {1})
        for item in self.items("utility"):
            attribute, subject = item["query"].split()
            expected = {
                label: utility.grade(memory, subject, attribute)
                for label, memory in self.memory.items()
                if utility.grade(memory, subject, attribute) and self.sees(item["audience"], label)
            }
            self.assertEqual(item["gold"], expected)
            self.assertIn(2, item["gold"].values())
        for item in self.items("ceiling"):
            attribute, subject = item["query"].split()
            self.assertEqual(
                set(item["gold"]),
                {label for label, m in self.memory.items() if utility.grade(m, subject, attribute)},
            )
        for item in self.items("leakage"):
            self.assertFalse(self.sees(item["audience"], item["canary"]))
            self.assertIn(self.memory[item["canary"]]["value"], item["query"].split())

    def test_each_arm_shows_what_it_should(self):
        for item in self.trial["items"]:
            audience = item["audience"]
            for arm, shown in item["shown"].items():
                if arm != "pooled" and item["type"] != "ceiling":
                    for label in shown:
                        self.assertTrue(self.sees(audience, label), (item["type"], arm, label))
            if item["type"] == "utility":
                built = item["shown"]["built"]
                self.assertEqual(item["shown"]["fault-swap-top"], built[1:2] + built[:1] + built[2:])
                self.assertEqual(
                    item["shown"]["after-k"],
                    [label for label in item["shown"]["pooled"] if self.sees(audience, label)],
                )
                self.assertLessEqual(set(built), set(self.memory))
                self.assertEqual(len(item["shown"]["after-all"]), utility.K)

    def test_the_workload_is_below_the_ceiling(self):
        scores = self.trial["scores"]
        self.assertLess(scores["ceiling"]["mean_rr"], 1.0)
        self.assertGreater(scores["utility"]["after_all_ndcg_below_one"], 0)
        self.assertLess(scores["utility"]["metrics"]["after-all"]["recall"], 1.0)

    def test_the_faults_cost_utility_on_items(self):
        compared = self.trial["scores"]["utility"]["items_compared"]
        drop = compared["drop_term_minus_after_all"]["ndcg"]
        self.assertGreater(drop["lower"], drop["higher"])
        swap = compared["swap_top_minus_after_all"]["rr"]
        self.assertGreater(swap["lower"], swap["higher"])

    def test_a_hard_trial_is_reproducible(self):
        self.assertEqual(utility.hard_run_trial(SEED), self.trial)

    def test_the_fault_option_replaces_only_the_built_arm(self):
        faulty = utility.hard_run_trial(SEED, "fault-swap-top")
        for clean, broken in zip(self.trial["items"], faulty["items"]):
            if clean["type"] == "utility":
                self.assertEqual(broken["shown"]["built"], clean["shown"]["fault-swap-top"])
                self.assertEqual(
                    {k: v for k, v in broken["shown"].items() if k != "built"},
                    {k: v for k, v in clean["shown"].items() if k != "built"},
                )
            else:
                self.assertEqual(broken, clean)


class HardRunTests(unittest.TestCase):
    """End to end over a few seeds: the controls fire and a planted fault is caught."""

    @classmethod
    def setUpClass(cls):
        cls.seeds = range(3)
        cls.trials = [utility.hard_run_trial(seed) for seed in cls.seeds]

    def test_report_controls_and_serialisation(self):
        report = utility.hard_report_for(self.trials, [utility.hard_run_trial(0)])
        json.dumps(report)
        decision = report["decision"]
        self.assertTrue(decision["rule_1_pooled_leaks"])
        self.assertTrue(decision["rule_1_owner_finds_canary"])
        self.assertTrue(decision["rule_2_no_over_blocking"])
        self.assertTrue(decision["rule_3_below_ceiling"])
        self.assertTrue(decision["rule_4_by_fault"]["drop_term_minus_after_all"])
        self.assertTrue(decision["rule_5_deterministic"])
        self.assertTrue(decision["rule_6_zero_leakage"])
        text = utility.hard_render(report)
        self.assertIn("**Verdict: {}**".format(decision["verdict"]), text)
        for arm in utility.H_ARMS:
            self.assertIn(utility.H_ARM_LABELS[arm], text)

    def test_a_changed_rerun_fails_determinism(self):
        changed = json.loads(json.dumps(self.trials[0]))
        changed["items"][0]["shown"]["built"].reverse()
        report = utility.hard_report_for(self.trials, [changed])
        self.assertFalse(report["decision"]["rule_5_deterministic"])
        self.assertEqual(report["decision"]["verdict"], "inconclusive (a control failed)")

    def test_a_drop_term_store_is_read_as_a_utility_cost(self):
        broken = [utility.hard_run_trial(seed, "fault-drop-term") for seed in self.seeds]
        decision = utility.hard_report_for(broken, broken[:1], "fault-drop-term")["decision"]
        self.assertEqual(decision["rule_7_utility"]["ndcg"], "utility cost")
        # The verdict itself also needs rule 4 (three seeds may not settle swap-top).
        self.assertTrue(decision["reasons"][0].startswith("rule 7, utility cost on nDCG@10"))
        self.assertNotEqual(decision["verdict"], "H1 supported")

    def test_a_store_that_ignores_viewers_fails_rule_6(self):
        workspace = utility.hard_build_workspace(SEED)
        asked = utility.hard_questions(workspace)
        with mock.patch.object(utility.MemoryStore, "search", search_ignoring_viewers):
            with utility.MemoryStore(":memory:") as store:
                labels, _ = utility.populate(store, workspace)
                items = utility.hard_answer(store, labels, workspace, asked)
        broken = dict(self.trials[0], items=items, scores=utility.hard_score_items(items))
        decision = utility.hard_report_for([broken], [broken])["decision"]
        self.assertFalse(decision["rule_6_zero_leakage_by_arm"]["built"])
        self.assertTrue(decision["rule_6_zero_leakage_by_arm"]["after-all"])

    def test_main_hard_writes_both_files(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "hard"
            with mock.patch("sys.stdout", io.StringIO()):
                utility.main(["--hard", "--trials", "1", "--output", str(output)])
            report = json.loads(output.with_suffix(".json").read_text())
            self.assertEqual((report["mode"], report["fault"], report["trials"]), ("hard", None, 1))
            self.assertEqual(report["summary"]["determinism"]["seeds"], [0])
            self.assertTrue(output.with_suffix(".md").read_text().startswith("# Zero leakage"))


if __name__ == "__main__":
    unittest.main()
