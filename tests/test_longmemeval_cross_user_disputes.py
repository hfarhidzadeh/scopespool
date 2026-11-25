import contextlib
import importlib.util
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "experiments" / "longmemeval_cross_user_disputes.py"
spec = importlib.util.spec_from_file_location("longmemeval_cross_user_disputes", SCRIPT)
cd = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = cd
spec.loader.exec_module(cd)

QUESTION = {
    "question_id": "q1",
    "question_type": "knowledge-update",
    "question": "What is my personal best time?",
    "answer": "25:50",
    "question_date": "2023/06/01 (Thu) 00:58",
    "haystack_session_ids": ["early", "late"],
    "haystack_dates": ["2023/05/25 (Thu) 20:21", "2023/05/27 (Sat) 10:20"],
    "haystack_sessions": [
        [{"role": "user", "content": "I ran a charity race."},
         {"role": "assistant", "content": "Nice."},
         {"role": "user", "content": "My personal best time is 27:12.", "has_answer": True},
         {"role": "user", "content": "Can you recommend running shoes?"},
         {"role": "user", "content": "I also swim on Sundays."}],
        [{"role": "user", "content": "New personal best: 25:50!", "has_answer": True},
         {"role": "user", "content": "Recommend a book."},
         {"role": "user", "content": "My dog is called Pepper."},
         {"role": "user", "content": "I live near the river."}],
    ],
}
ANNOTATIONS = {"q1": {"category": "current", "required_groups": [["late:0"]],
                      "supersession": [{"old": "early:2", "new": "late:0",
                                        "relation": "supersedes"}]}}


def pair():
    return cd.make_pairs([QUESTION], ANNOTATIONS)[0][0]


class PairTests(unittest.TestCase):
    def test_a_pair_is_the_real_older_and_newer_text(self):
        pairs, counts = cd.make_pairs([QUESTION], ANNOTATIONS)
        self.assertEqual((pairs[0]["older"], pairs[0]["newer"]),
                         ("My personal best time is 27:12.", "New personal best: 25:50!"))
        self.assertNotIn(pairs[0]["older"], pairs[0]["pool"])
        self.assertEqual(len(pairs[0]["pool"]), 6)
        self.assertEqual(counts, {"edges": 1, "dropped_identical": 0, "pairs": 1, "questions": 1})

    def test_only_supersedes_edges_of_current_questions_and_distinct_texts_count(self):
        for category, relation in (("previous", "supersedes"), ("current", "adds_to")):
            other = {"q1": dict(ANNOTATIONS["q1"], category=category,
                                supersession=[dict(ANNOTATIONS["q1"]["supersession"][0],
                                                   relation=relation)])}
            self.assertEqual(cd.make_pairs([QUESTION], other)[0], [])
        same = json.loads(json.dumps(QUESTION))
        same["haystack_sessions"][1][0]["content"] = "  my PERSONAL best time is 27:12. "
        pairs, counts = cd.make_pairs([same], ANNOTATIONS)
        self.assertEqual((pairs, counts["dropped_identical"]), ([], 1))


class TrialTests(unittest.TestCase):
    def test_a_trial_is_a_function_of_its_seed(self):
        self.assertEqual(cd.make_trial(pair(), 0, 3), cd.make_trial(pair(), 0, 3))
        json.dumps(cd.run_trial(pair(), 0, 3))

    def test_the_hidden_claims_come_after_the_older_claim(self):
        for rep in range(20):
            trial = cd.make_trial(pair(), 0, rep)
            older_at = next(i for i, s in enumerate(trial["visible"]) if s.get("name") == "older")
            self.assertTrue(all(c["position"] > older_at for c in trial["hidden"]))
            self.assertNotEqual(trial["older_speaker"], trial["newer_speaker"])

    def test_the_current_store_passes_every_check(self):
        for rep in range(12):
            result = cd.run_trial(pair(), 0, rep)
            self.assertEqual(set(result["checks"].values()), {True}, (rep, result))

    def test_an_admin_claim_in_view_can_close_the_dispute(self):
        closed = [cd.run_trial(pair(), 0, rep) for rep in range(30)]
        self.assertTrue(any(r["v_closed"] for r in closed))
        self.assertTrue(all(r["dana_claims"] for r in closed if r["v_closed"]))


class FaultTests(unittest.TestCase):
    def setUp(self):
        restore = (cd.MemoryStore.disputes, cd.MemoryStore.who_knows)
        self.addCleanup(setattr, cd.MemoryStore, "who_knows", restore[1])
        self.addCleanup(setattr, cd.MemoryStore, "disputes", restore[0])

    def test_computing_over_every_memory_fails_noninterference(self):
        cd.install_fault("administrative")
        results = [cd.run_trial(pair(), 0, rep) for rep in range(8)]
        self.assertEqual([r["checks"]["noninterference"] for r in results], [False] * 8)
        self.assertTrue(all(r["checks"]["determinism"] for r in results))

    def test_an_unknown_fault_is_rejected(self):
        with self.assertRaises(ValueError):
            cd.install_fault("unknown")


class DecisionRuleTests(unittest.TestCase):
    def summary(self, trials, **failed):
        return {"checks": {name: {"held": trials - len(failed.get(name, ())),
                                  "not_held": list(failed.get(name, ()))} for name in cd.CHECKS}}

    def verdict(self, trials=10, **failed):
        return cd.decide(self.summary(trials, **failed), trials)["verdict"]

    def test_verdicts(self):
        self.assertEqual(self.verdict(), "disputes and who-knows pass on real text")
        self.assertEqual(self.verdict(noninterference=["3/1", "4/0"]),
                         "they fail rule 6 (first failing trial 3/1)")
        self.assertEqual(self.verdict(detection=["0/0"], noninterference=["1/1"]),
                         "inconclusive (control 2 failed)")
        self.assertEqual(self.verdict(power=[str(i) for i in range(6)]),
                         "inconclusive (control 3 failed)")
        self.assertEqual(self.verdict(power=[str(i) for i in range(5)]),
                         "disputes and who-knows pass on real text")

    def test_fault_validation_needs_a_quarter(self):
        self.assertTrue(cd.validate_fault(self.summary(8, noninterference=["a", "b"]), 8)["detected"])
        self.assertFalse(cd.validate_fault(self.summary(8, noninterference=["a"]), 8)["detected"])


class MainTests(unittest.TestCase):
    def test_main_writes_the_report_and_restores_the_store(self):
        before = (cd.MemoryStore.disputes, cd.MemoryStore.who_knows)
        with tempfile.TemporaryDirectory() as directory:
            data, notes = Path(directory) / "d.json", Path(directory) / "a.json"
            data.write_text(json.dumps([QUESTION]))
            notes.write_text(json.dumps({"annotations": ANNOTATIONS}))
            output = Path(directory) / "report"
            with contextlib.redirect_stdout(io.StringIO()) as printed:
                cd.main(["--data", str(data), "--annotations", str(notes), "--reps", "3",
                         "--fault", "administrative", "--output", str(output)])
            report = json.loads(output.with_suffix(".json").read_text())
            text = output.with_suffix(".md").read_text()
        self.assertEqual((report["trials"], report["pairs"]["pairs"]), (3, 1))
        self.assertTrue(report["validation"]["detected"])
        self.assertIn(report["decision"]["verdict"], text)
        self.assertEqual(printed.getvalue().strip(), text.strip())
        self.assertEqual((cd.MemoryStore.disputes, cd.MemoryStore.who_knows), before)


if __name__ == "__main__":
    unittest.main()
