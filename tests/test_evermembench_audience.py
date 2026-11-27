import contextlib
import importlib.util
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

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
