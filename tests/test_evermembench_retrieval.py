import contextlib
import importlib.util
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "experiments" / "evermembench_retrieval.py"
spec = importlib.util.spec_from_file_location("evermembench_retrieval", SCRIPT)
retrieval = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = retrieval
spec.loader.exec_module(retrieval)


def fixture(topic, vocabulary=None):
    """One day, two groups of 12 messages; three questions with 1, 2 and 11 R entries."""
    word = vocabulary or "t{}w".format(topic)
    groups = {name: [{"message_index": i, "speaker": "Ada", "time": "2025-01-01 09:00:00",
                      "dialogue": "{}{}{} filler note".format(word, name[-1], i)}
                     for i in range(1, 13)] for name in ("Group 1", "Group 2")}
    days = [{"topic_id": topic, "date": "2025-01-01", "dialogues": groups}]

    def ref(group, index):
        return {"date": "2025-01-01", "group": group, "message_index": str(index)}

    questions = [
        {"topic_id": topic, "id": "F_SH_Top{}_001".format(topic), "Q": "{}13".format(word),
         "R": [ref("Group 1", 3)]},
        {"topic_id": topic, "id": "F_MH_Top{}_002".format(topic),
         "Q": "{}15 {}22".format(word, word), "R": [ref("Group 1", 5), ref("Group 2", 2)]},
        {"topic_id": topic, "id": "MA_P_Top{}_003".format(topic),
         "Q": " ".join("{}1{}".format(word, i) for i in range(1, 12)),
         "R": [ref("Group 1", i) for i in range(1, 12)]},
    ]
    return days, questions


def distinct(root, topic):
    return fixture(topic)


def identical(root, topic):
    return fixture(topic, vocabulary="same")


def run(reader, **options):
    with patch.object(retrieval, "read_topic_files", reader), \
            contextlib.redirect_stderr(io.StringIO()):
        return [retrieval.run_topic((Path("unused"), t, options.get("limit"), "ngram", True))
                for t in retrieval.TOPICS]


def canary_of(rows):
    canaries = [row.pop("canary") for row in rows]
    return {"source": "run here", "reasons": [], "topics": canaries,
            "passed": all(c["all_required_at_10"] == 1.0 and c["unplanted_token_hits"] == 0
                          for c in canaries)}


class ScoringTests(unittest.TestCase):
    def test_all_required_needs_every_group_and_is_undefined_above_ten(self):
        self.assertEqual(retrieval.score([["a"], ["b", "c"]], ["a", "b", "c"], ["c", "x", "a"]),
                         {"all_required": 1.0, "group_coverage": 1.0, "rr": 1.0})
        missing = retrieval.score([["a"], ["b"]], ["a", "b"], ["x", "b"])
        self.assertEqual((missing["all_required"], missing["group_coverage"], missing["rr"]),
                         (0.0, 0.5, 0.5))
        wide = [[str(i)] for i in range(11)]
        self.assertIsNone(retrieval.score(wide, [g[0] for g in wide], [g[0] for g in wide])
                          ["all_required"])

    def test_cohorts_and_question_types(self):
        self.assertEqual([retrieval.cohort(n) for n in (1, 2, 3, 4, 10, 11)],
                         ["1", "2-3", "2-3", "4-10", "4-10", ">10"])
        self.assertEqual(retrieval.question_type("MA_C_Top03_101"), "MA_C")
        self.assertEqual(retrieval.question_type("odd"), "other")

    def test_holm_adjusts_in_order_and_stays_monotone(self):
        self.assertEqual(retrieval.holm({"A": 0.01, "B": 0.04}), {"A": 0.02, "B": 0.04})
        self.assertEqual(retrieval.holm({"A": 0.03, "B": 0.02}), {"B": 0.04, "A": 0.04})


class ControlTests(unittest.TestCase):
    def test_distinct_topics_pass_every_control(self):
        rows = run(distinct)
        analysis = retrieval.analyse(rows, canary_of(rows))
        controls = analysis["controls"]
        self.assertTrue(controls["C0"]["passed"])
        self.assertTrue(controls["C1"]["passed"])
        self.assertEqual(controls["C1"]["eligible"], 10)  # 2 eligible questions in 5 topics
        self.assertTrue(controls["C2"]["passed"])
        self.assertEqual(controls["C2"]["all_required"], 0.0)
        self.assertNotIn("inconclusive", analysis["decision"]["verdict"])
        lexical = analysis["tables"]["cohort"]["1"]["lexical"]
        self.assertEqual(lexical["all_required"], 1.0)
        self.assertIsNone(analysis["tables"]["cohort"][">10"]["lexical"]["all_required"])

    def test_shared_content_across_topics_fails_the_shuffle_control(self):
        rows = run(identical)
        analysis = retrieval.analyse(rows, canary_of(rows))
        self.assertFalse(analysis["controls"]["C2"]["passed"])
        self.assertEqual(analysis["decision"]["verdict"], "inconclusive (control C2 failed)")

    def test_a_failed_canary_makes_the_run_inconclusive(self):
        rows = run(distinct)
        canary_of(rows)
        failed = {"source": "given", "reasons": ["code changed since the control"], "passed": False}
        self.assertEqual(retrieval.analyse(rows, failed)["decision"]["verdict"],
                         "inconclusive (control C0 failed)")

    def test_a_recorded_control_is_refused_when_code_or_scope_differs(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "control.json"
            path.write_text(json.dumps({"rule": "token-only", "fault": None, "passed": True,
                                        "topics_run": ["01"],
                                        "code_sha256": {"src/dynmemory/store.py": "0" * 64}}))
            verdict = retrieval.accepted_control(path, ["01"], None)
        self.assertFalse(verdict["passed"])
        self.assertIn("code changed since the control", verdict["reasons"])


class ApprovalTests(unittest.TestCase):
    def quiet(self, argv):
        with contextlib.redirect_stderr(io.StringIO()) as err, \
                contextlib.redirect_stdout(io.StringIO()):
            code = retrieval.main(argv)
        return code, err.getvalue()

    def test_a_recorded_run_is_refused_without_approval(self):
        with patch.object(retrieval, "run_topic", side_effect=AssertionError("must not run")):
            code, message = self.quiet(["--data", "unused"])
        self.assertEqual(code, 2)
        self.assertIn("--approved", message)

    def test_a_smoke_run_must_write_outside_the_results_folder(self):
        results = retrieval.ROOT / "experiments" / "results" / "smoke.json"
        with patch.object(retrieval, "run_topic", side_effect=AssertionError("must not run")):
            self.assertEqual(self.quiet(["--data", "unused", "--smoke"])[0], 2)
            self.assertEqual(self.quiet(["--data", "unused", "--smoke", "--output",
                                         str(results)])[0], 2)

    def test_a_smoke_run_writes_a_marked_report(self):
        with tempfile.TemporaryDirectory() as tmp, \
                patch.object(retrieval, "read_topic_files", distinct):
            output = Path(tmp) / "smoke.json"
            code, _ = self.quiet(["--data", "unused", "--smoke", "--output", str(output)])
            report = json.loads(output.read_text())
            text = output.with_suffix(".md").read_text()
        self.assertEqual(code, 0)
        self.assertEqual(report["status"], "SMOKE, not a recorded run")
        self.assertEqual(report["topics_run"], ["01"])
        self.assertIn("SMOKE", text)


if __name__ == "__main__":
    unittest.main()
