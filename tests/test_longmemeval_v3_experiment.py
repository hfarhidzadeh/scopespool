import contextlib
import importlib.util
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

from dynmemory import longmemeval_v3 as v3

SCRIPT = Path(__file__).resolve().parents[1] / "experiments" / "longmemeval_v3.py"
spec = importlib.util.spec_from_file_location("longmemeval_v3_experiment", SCRIPT)
ex = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = ex
spec.loader.exec_module(ex)

CATEGORIES = ["current", "current", "previous", "both", "both", "latest_event", "context"]


def fixture(count=len(CATEGORIES)):
    questions, labels = [], {}
    for number in range(count):
        word = "topic{}x".format(number)
        questions.append({
            "question_id": "q{}".format(number),
            "question_type": "knowledge-update",
            "question": "What is my {} count?".format(word),
            "answer": "9", "question_date": "2023/06/01 (Thu) 10:00",
            "haystack_session_ids": ["a{}".format(number), "b{}".format(number), "c{}".format(number)],
            "haystack_dates": ["2023/05/01 (Mon) 10:00", "2023/05/10 (Wed) 10:00", "2023/05/05 (Fri) 10:00"],
            "haystack_sessions": [
                [{"role": "user", "content": "My {} count is 3 so far.".format(word), "has_answer": True}],
                [{"role": "user", "content": "My {} count is now 9 in total.".format(word), "has_answer": True}],
                [{"role": "user", "content": "Filler talk about weather and lunch plans {}.".format(number)}],
            ],
            "answer_session_ids": [],
        })
        labels["q{}".format(number)] = {"category": CATEGORIES[number]}
    return questions, labels


QUESTIONS, LABELS = fixture()
ANNOTATIONS = v3.derive_annotations(QUESTIONS, LABELS)
EVAL_SETS, _ = v3.convert(QUESTIONS, ANNOTATIONS)


def stats(mean, p):
    return {"mean": mean, "ci95": [mean - 0.1, mean + 0.1], "p": p, "better": 0, "worse": 0,
            "same": 0, "questions": 5}


class ReadingTests(unittest.TestCase):
    def test_readings_need_a_nonzero_change_with_a_small_p(self):
        self.assertEqual(ex.reading(stats(0.2, 0.01), "A"), "helps")
        self.assertEqual(ex.reading(stats(-0.2, 0.01), "A"), "hurts")
        self.assertEqual(ex.reading(stats(-0.2, 0.01), "B"), "hurts")
        self.assertEqual(ex.reading(stats(0.2, 0.01), "C"), "better")
        self.assertEqual(ex.reading(stats(-0.2, 0.01), "C"), "worse")
        self.assertEqual(ex.reading(stats(0.2, 0.2), "A"), "no clear effect")
        self.assertEqual(ex.reading(stats(0.0, 0.001), "A"), "no clear effect")
        self.assertEqual(ex.reading(None, "A"), "no questions")

    def test_a_failed_control_makes_the_run_inconclusive(self):
        main = {"A": {e: stats(0, 1) for e in ex.EMBEDDERS}, "B": {e: stats(0, 1) for e in ex.EMBEDDERS},
                "C": stats(0, 1)}
        good = {"c1_unchanged": True, "c2_zero": True, "c3_shift": 0.0}
        self.assertEqual(ex.decide(good, main)["failed_controls"], [])
        self.assertEqual(ex.decide(dict(good, c1_unchanged=False), main)["verdict"],
                         "inconclusive (control C1 failed)")
        self.assertEqual(ex.decide(dict(good, c2_zero=False, c3_shift=0.5), main)["verdict"],
                         "inconclusive (control C2, C3 failed)")


class ControlConstructionTests(unittest.TestCase):
    def test_archiving_every_required_turn_leaves_nothing_required_findable(self):
        for eval_set in EVAL_SETS:
            archived = ex.archive_required(eval_set)
            required = {k for g in eval_set["queries"][0]["required_groups"] for k in g}
            self.assertEqual({u["old"] for u in archived["updates"]}, required)
            rows = ex.evaluate([archived], None, True)
            self.assertEqual(rows[0]["all_required"], 0.0)

    def test_random_archiving_never_touches_required_turns_and_is_seeded(self):
        for eval_set in EVAL_SETS:
            required = {k for g in eval_set["queries"][0]["required_groups"] for k in g}
            first = ex.archive_random(eval_set, 0)
            self.assertFalse({u["old"] for u in first["updates"]} & required)
            self.assertEqual(first, ex.archive_random(eval_set, 0))


class RunTests(unittest.TestCase):
    def test_the_old_metric_hides_the_harm_that_all_required_shows(self):
        rows = {(e, u): ex.evaluate(EVAL_SETS, None, u == "applied")
                for e in ("lexical",) for u in ("kept", "applied")}
        both = [r for r in rows[("lexical", "applied")] if r["tags"][-1] == "both"]
        self.assertTrue(both)
        self.assertTrue(all(r["first_hit"] == 1.0 for r in both))
        self.assertTrue(all(r["all_required"] == 0.0 for r in both))
        kept = [r for r in rows[("lexical", "kept")] if r["tags"][-1] == "both"]
        self.assertTrue(all(r["all_required"] == 1.0 for r in kept))

    def test_main_writes_a_report_with_all_controls_holding(self):
        with tempfile.TemporaryDirectory() as directory:
            data, notes = Path(directory) / "d.json", Path(directory) / "a.json"
            data.write_text(json.dumps(QUESTIONS))
            notes.write_text(json.dumps({"annotations": ANNOTATIONS}))
            output = Path(directory) / "report"
            with contextlib.redirect_stdout(io.StringIO()) as printed:
                ex.main(["--data", str(data), "--annotations", str(notes), "--semantic", "ngram",
                         "--output", str(output)])
            report = json.loads(output.with_suffix(".json").read_text())
            text = output.with_suffix(".md").read_text()
        self.assertEqual(report["decision"]["failed_controls"], [])
        self.assertEqual(report["main"]["questions"], len(EVAL_SETS))
        self.assertIn(report["decision"]["verdict"], text)
        self.assertEqual(printed.getvalue().strip(), text.strip())


if __name__ == "__main__":
    unittest.main()
