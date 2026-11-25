import importlib.util
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "experiments/longmemeval_history_retrieval.py"
SPEC = importlib.util.spec_from_file_location("longmemeval_history_retrieval", SCRIPT)
pilot = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pilot)


def fixture(name, *, category="current", distractors=0, update=True):
    memories = {"old": {"content": "widget widget widget", "kind": "episode"}}
    memories.update({
        f"other{i}": {"content": f"widget details {i}", "kind": "episode"}
        for i in range(distractors)
    })
    memories["new"] = {
        "content": "widget color described using many other unrelated filler terms",
        "kind": "episode",
    }
    needed = ["old", "new"] if category == "both" else ["new"]
    return {
        "id": name,
        "memories": memories,
        "links": [],
        "updates": [{"old": "old", "new": "new"}] if update else [],
        "queries": [{
            "query": "widget",
            "tags": [category],
            "relevant": needed,
            "required_groups": [[key] for key in needed],
            "stale": ["old"] if "old" not in needed and update else [],
        }],
    }


class HistoryRetrievalTests(unittest.TestCase):
    def test_demotion_considers_a_relevant_match_outside_the_initial_top_ten(self):
        item = fixture("late", distractors=9)
        results = pilot.evaluate([item], {"late": "current"})

        self.assertEqual(results["summary"]["kept"]["current intent"]["all_required"], 0)
        self.assertEqual(results["summary"]["demote_current"]["current intent"]["all_required"], 1)
        self.assertTrue(all(results["controls"].values()))

    def test_supplied_history_intent_keeps_both_required_groups_searchable(self):
        both = fixture("history", category="both")
        unchanged = fixture("no-edge", update=False)
        results = pilot.evaluate([both, unchanged], {"history": "history", "no-edge": "current"})
        summary = results["summary"]

        self.assertEqual(summary["kept"]["older-required evidence"]["all_required"], 1)
        self.assertEqual(summary["archive"]["older-required evidence"]["all_required"], 0)
        self.assertEqual(summary["demote_current"]["older-required evidence"]["all_required"], 1)
        self.assertTrue(all(results["controls"].values()))


if __name__ == "__main__":
    unittest.main()
