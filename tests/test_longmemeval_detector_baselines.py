import contextlib
import copy
import importlib.util
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from dynmemory import longmemeval_v3 as v3

SCRIPT = Path(__file__).resolve().parents[1] / "experiments" / "longmemeval_detector_baselines.py"
spec = importlib.util.spec_from_file_location("longmemeval_detector_baselines_experiment", SCRIPT)
db = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = db
spec.loader.exec_module(db)

CATEGORIES = ["current", "current", "previous", "both", "latest_event", "context"]
FILLER = ["lunch plans {} and weather talk", "a book review number {} was fun",
          "gym session {} went well today", "cooking pasta {} for dinner tonight"]


def fixture():
    questions, labels = [], {}
    for number, category in enumerate(CATEGORIES):
        word = "topic{}x".format(number)
        filler = [{"role": "user", "content": FILLER[i % 4].format(number * 100 + i)} for i in range(40)]
        questions.append({
            "question_id": "q{}".format(number), "question_type": "knowledge-update",
            "question": "What is my {} count?".format(word), "answer": "9",
            "question_date": "2023/06/01 (Thu) 10:00",
            "haystack_session_ids": ["a{}".format(number), "f{}".format(number), "b{}".format(number)],
            "haystack_dates": ["2023/05/01 (Mon) 10:00", "2023/05/05 (Fri) 10:00", "2023/05/10 (Wed) 10:00"],
            "haystack_sessions": [
                [{"role": "user", "content": "My {} count is 3 so far.".format(word), "has_answer": True}],
                filler,
                [{"role": "user", "content": "My {} count is now 9 in total.".format(word), "has_answer": True}],
            ],
            "answer_session_ids": [],
        })
        labels["q{}".format(number)] = {"category": category}
    return questions, labels


QUESTIONS, LABELS = fixture()
ANNOTATIONS = v3.derive_annotations(QUESTIONS, LABELS)


def items():
    eval_sets, _ = v3.convert(QUESTIONS, ANNOTATIONS)
    wanted = {s["id"]: s for s in eval_sets}
    return [db.prepare(q, ANNOTATIONS[q["question_id"]], wanted[q["question_id"]]) for q in QUESTIONS]


class PrepareTests(unittest.TestCase):
    def test_new_turn_targets_and_controls(self):
        for p in items():
            self.assertEqual(p["new"].split(":")[0][0], "b")
            self.assertEqual(p["positive"], p["category"] in ("current", "previous", "both"))
            if p["positive"]:
                self.assertEqual([t.split(":")[0][0] for t in p["targets"]], ["a"])
            for key in p["controls"]:
                self.assertGreaterEqual(p["position"][key], db.MIN_POSITION)
                self.assertNotIn(key, {p["new"], *p["targets"]})
            self.assertLessEqual(len(p["controls"]), db.CONTROL_TURNS)

    def test_candidates_come_only_from_earlier_turns_and_find_the_old_value(self):
        for p in items():
            self.assertLessEqual(len(p["cands_new"]), db.CANDIDATES)
            for key, _ in p["cands_new"]:
                self.assertLess(p["position"][key], p["position"][p["new"]])
            if p["positive"]:
                self.assertIn(p["targets"][0], [k for k, _ in p["cands_new"]])

    def test_positive_uses_annotated_confirmation_and_excludes_it_from_controls(self):
        question = copy.deepcopy(QUESTIONS[0])
        question["haystack_sessions"][-1].extend([
            {"role": "assistant", "content": "Do you want to confirm that?"},
            {"role": "user", "content": "Yes, my topic0x count is now 9 in total."},
        ])
        annotation = copy.deepcopy(ANNOTATIONS["q0"])
        annotation["supersession"][0]["new"] = "b0:2"
        annotation["required_groups"] = [["b0:2"]]
        eval_set, _ = v3.convert_question(question, annotation)
        with mock.patch.object(db, "CONTROL_TURNS", 100):
            prepared = db.prepare(question, annotation, eval_set)
        self.assertEqual(prepared["new"], "b0:2")
        self.assertEqual(prepared["targets"], ["a0:0"])
        self.assertNotIn("b0:2", prepared["controls"])

    def test_negative_keeps_latest_marked_turn_as_probe(self):
        prepared = next(p for p in items() if p["category"] == "context")
        self.assertEqual(prepared["new"], "b5:0")


class DetectorTests(unittest.TestCase):
    def setUp(self):
        self.items = items()

    def test_never_and_top_and_oracle_behave_as_controls(self):
        never = db.run_detector(db.Never(), self.items)
        self.assertTrue(all(d["new"] is None and not any(d["controls"]) for d in never.values()))
        top = db.run_detector(db.Top(), self.items)
        self.assertTrue(all(d["new"] is not None for d in top.values()))
        outcome = db.run_all(self.items, db.CachedEmbedder(db.NGramHashEmbedder()))
        self.assertEqual(db.check_controls(self.items, outcome),
                         {"c1_never_is_none": True, "c2_oracle_candidate": True})
        score = outcome["readings"]["oracle-cand"]["score"]
        self.assertEqual(score["positives"]["correct"], score["positives"]["n"])
        self.assertEqual(score["negatives"]["fired"], 0)

    def test_applying_a_wrong_decision_can_archive_required_evidence(self):
        item = next(p for p in self.items if p["category"] == "previous")
        wrong = {item["id"]: {"new": item["targets"][0], "controls": []}}
        sets = db.sets_for([item], wrong)
        row = db.retrieval(sets, True)[0]
        self.assertEqual(row["all_required"], 0.0)

    def test_expected_random_recall_counts_targets_among_candidates(self):
        for p in self.items:
            hit = bool({k for k, _ in p["cands_new"]} & set(p["targets"]))
            self.assertEqual(db.expected_random_recall(p), (1 / db.CANDIDATES) if hit else 0.0)

    def test_conditions_name_every_failed_requirement(self):
        score = {"current": {"recall": 0.1}, "controls": {"n": 100, "fired": 50},
                 "negatives": {"n": 10, "fired": 5}}
        bad = {"score": score, "vs_random": None, "recovery": 0.1, "rr_gain": None}
        self.assertEqual([f.split(":")[0] for f in db.conditions(bad)], ["a", "b", "c", "d", "e"])
        good_stats = {"mean": 0.1, "p": 0.01}
        good = {"score": {"current": {"recall": 0.9}, "controls": {"n": 100, "fired": 1},
                          "negatives": {"n": 10, "fired": 0}},
                "vs_random": good_stats, "recovery": 0.9, "rr_gain": good_stats}
        self.assertEqual(db.conditions(good), [])


class MainTests(unittest.TestCase):
    def test_main_writes_a_report(self):
        with tempfile.TemporaryDirectory() as directory:
            data, notes = Path(directory) / "d.json", Path(directory) / "a.json"
            data.write_text(json.dumps(QUESTIONS))
            notes.write_text(json.dumps({"annotations": ANNOTATIONS, "review": {
                "category_approval": {"date": "2026-11-25", "decisions": {"q0": "current"}}
            }}))
            output = Path(directory) / "report"
            with contextlib.redirect_stdout(io.StringIO()) as printed:
                db.main(["--data", str(data), "--annotations", str(notes), "--semantic", "ngram",
                         "--output", str(output)])
            report = json.loads(output.with_suffix(".json").read_text())
            text = output.with_suffix(".md").read_text()
        self.assertTrue(all(report["controls"].values()))
        self.assertIn(report["verdict"], text)
        self.assertIn("accepted 1 proposed category decisions", text)
        self.assertEqual(printed.getvalue().strip(), text.strip())


if __name__ == "__main__":
    unittest.main()
