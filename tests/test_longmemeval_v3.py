import contextlib
import copy
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from dynmemory import MemoryStore  # noqa: F401  (import check)
from dynmemory import evaluation, longmemeval_v3 as v3
from dynmemory.evaluation import load_eval_set, query_rows

QUESTION = {
    "question_id": "q1",
    "question_type": "knowledge-update",
    "question": "What is my personal best time?",
    "answer": "25:50",
    "question_date": "2023/06/01 (Thu) 00:58",
    "haystack_session_ids": ["late", "early", "filler"],
    "haystack_dates": ["2023/05/27 (Sat) 10:20", "2023/05/25 (Thu) 20:21", "2023/05/26 (Fri) 09:00"],
    "haystack_sessions": [
        [{"role": "user", "content": "Training again; hoping to beat my 25:50.", "has_answer": True},
         {"role": "assistant", "content": "Good luck!"}],
        [{"role": "user", "content": "I ran a charity race."},
         {"role": "assistant", "content": "Nice."},
         {"role": "user", "content": "My personal best time is 27:12.", "has_answer": True}],
        [{"role": "user", "content": "Recommend a book."},
         {"role": "assistant", "content": "Try Dune."}],
    ],
    "answer_session_ids": ["late", "early"],
}
OLD, NEW = "early:2", "late:0"


def question(question_id="q1", **changes):
    changed = copy.deepcopy(QUESTION)
    changed["question_id"] = question_id
    changed.update(changes)
    return changed


def labels(category):
    return {"q1": {"category": category}}


class DeriveTests(unittest.TestCase):
    def derive(self, category, overrides=None):
        with mock.patch.dict(v3.OVERRIDES, overrides or {}, clear=False):
            return v3.derive_annotations([QUESTION], labels(category))["q1"]

    def test_a_current_question_needs_only_the_newer_turn_and_supersedes_the_older(self):
        entry = self.derive("current")
        self.assertEqual(entry["required_groups"], [[NEW]])
        self.assertEqual(entry["supersession"], [{"old": OLD, "new": NEW, "relation": "supersedes"}])

    def test_a_previous_question_needs_the_older_turn(self):
        self.assertEqual(self.derive("previous")["required_groups"], [[OLD]])

    def test_a_both_question_needs_two_groups(self):
        self.assertEqual(self.derive("both")["required_groups"], [[OLD], [NEW]])

    def test_separate_events_and_context_do_not_supersede_by_default(self):
        for category in ("latest_event", "context"):
            relations = {e["relation"] for e in self.derive(category)["supersession"]}
            self.assertEqual(relations, {"independent"}, category)

    def test_an_override_can_make_an_addition_and_keep_both_needed(self):
        entry = self.derive("both", {"q1": {"relation": "adds_to", "flag": "plus one"}})
        self.assertEqual(entry["supersession"][0]["relation"], "adds_to")
        self.assertEqual(entry["required_groups"], [[OLD], [NEW]])
        self.assertEqual(entry["flags"], ["plus one"])

    def test_an_override_can_change_the_category_and_keeps_the_original(self):
        entry = self.derive("current", {"q1": {"category": "exclude"}})
        self.assertEqual((entry["category"], entry["original_category"]), ("exclude", "current"))
        self.assertEqual((entry["required_groups"], entry["supersession"]), ([], []))

    def test_an_extra_confirming_turn_joins_the_newer_group(self):
        extra = question(haystack_sessions=[
            QUESTION["haystack_sessions"][0] + [{"role": "user", "content": "Yes, the new time stands."}],
            *QUESTION["haystack_sessions"][1:]])
        with mock.patch.dict(v3.OVERRIDES, {"q1": {"extra_new": "late:2"}}):
            entry = v3.derive_annotations([extra], labels("both"))["q1"]
        self.assertEqual(entry["required_groups"], [[OLD], [NEW, "late:2"]])
        with mock.patch.dict(v3.OVERRIDES, {"q1": {"extra_new": "late:9"}}):
            with self.assertRaises(ValueError):
                v3.derive_annotations([extra], labels("both"))


class ConvertTests(unittest.TestCase):
    def annotation(self, category, relation="supersedes", groups=None):
        groups = groups if groups is not None else v3.derive_annotations(
            [QUESTION], labels(category))["q1"]["required_groups"]
        return {"category": category, "required_groups": groups, "status": v3.STATUS, "flags": [],
                "supersession": [{"old": OLD, "new": NEW, "relation": relation}]}

    def test_only_supersedes_edges_become_updates(self):
        for relation, expected in (("supersedes", [{"old": OLD, "new": NEW}]),
                                   ("adds_to", None), ("independent", None)):
            eval_set, _ = v3.convert_question(QUESTION, self.annotation("both", relation))
            self.assertEqual(eval_set.get("updates"), expected, relation)

    def test_relevant_is_the_union_of_the_groups_and_stale_is_only_unneeded_old_turns(self):
        current, _ = v3.convert_question(QUESTION, self.annotation("current"))
        query = current["queries"][0]
        self.assertEqual((query["relevant"], query["stale"]), ([NEW], [OLD]))
        both, _ = v3.convert_question(QUESTION, self.annotation("both"))
        query = both["queries"][0]
        self.assertEqual((query["relevant"], query["required_groups"]), ([OLD, NEW], [[OLD], [NEW]]))
        self.assertEqual(query["stale"], [])
        self.assertIn("both", query["tags"])

    def test_excluded_abstention_and_missing_annotations(self):
        excluded = {"category": "exclude", "required_groups": [], "supersession": [], "status": v3.STATUS}
        self.assertEqual(v3.convert_question(QUESTION, excluded)[1], "excluded by annotation")
        self.assertEqual(v3.convert_question(question("x_abs"), None)[1], "abstention question")
        with self.assertRaises(ValueError):
            v3.convert_question(QUESTION, None)
        sets, outcomes = v3.convert([QUESTION], {})
        self.assertEqual((sets, outcomes["skipped: no annotation"]), ([], 1))

    def test_other_question_types_need_all_evidence_as_one_group(self):
        other = question("o1", question_type="single-session-user")
        eval_set, _ = v3.convert_question(other, None)
        query = eval_set["queries"][0]
        self.assertEqual(query["required_groups"], [query["relevant"]])
        self.assertNotIn("updates", eval_set)

    def test_a_converted_set_is_valid_for_the_evaluator(self):
        eval_set, _ = v3.convert_question(QUESTION, self.annotation("both"))
        load_eval_set(eval_set)


class AnnotationFileTests(unittest.TestCase):
    def write(self, annotations):
        handle = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
        self.addCleanup(Path(handle.name).unlink)
        json.dump({"annotations": annotations}, handle)
        handle.close()
        return handle.name

    def entry(self, **changes):
        base = {"category": "current", "required_groups": [["a"]], "supersession": []}
        base.update(changes)
        return base

    def test_a_valid_file_loads_and_invalid_ones_are_named(self):
        self.assertIn("q", v3.load_annotations(self.write({"q": self.entry()})))
        for bad in (self.entry(category="nope"), self.entry(required_groups=[]),
                    self.entry(required_groups=[[]]), self.entry(category="exclude"),
                    self.entry(supersession=[{"old": "a", "new": "b", "relation": "replaces"}])):
            with self.assertRaises(ValueError):
                v3.load_annotations(self.write({"q": bad}))

    def test_main_annotates_then_converts(self):
        with tempfile.TemporaryDirectory() as directory:
            data, labels_path = Path(directory) / "d.json", Path(directory) / "l.json"
            notes, suite = Path(directory) / "a.json", Path(directory) / "s.jsonl"
            data.write_text(json.dumps([QUESTION]))
            labels_path.write_text(json.dumps({"labels": labels("both")}))
            with contextlib.redirect_stdout(io.StringIO()):
                v3.main(["annotate", str(data), "--labels", str(labels_path), "--out", str(notes)])
                v3.main(["convert", str(data), "--annotations", str(notes), "--out", str(suite)])
            written = [json.loads(line) for line in suite.read_text().splitlines()]
        self.assertEqual(len(written), 1)
        self.assertEqual(written[0]["queries"][0]["required_groups"], [[OLD], [NEW]])


class RequiredEvidenceMetricTests(unittest.TestCase):
    def eval_set(self, groups, relevant=None):
        memories = {"a": "red apple tree", "b": "blue boat harbor", "c": "green car garage",
                    "d": "apple boat mix"}
        query = {"query": "apple boat", "required_groups": groups,
                 "relevant": relevant or [k for g in groups for k in g]}
        return {"id": "s", "memories": {k: {"content": v, "kind": "episode"} for k, v in memories.items()},
                "queries": [query]}

    def test_all_required_needs_every_group_and_a_group_needs_any_of_its_turns(self):
        row = query_rows([self.eval_set([["a"], ["b"]])], k=10, links_for=lambda s: [],
                         embedder_for=lambda s: None)[0]
        self.assertTrue(row["all_required"])
        self.assertEqual(row["group_coverage"], 1.0)
        miss = query_rows([self.eval_set([["a"], ["c"]])], k=10, links_for=lambda s: [],
                          embedder_for=lambda s: None)[0]
        self.assertFalse(miss["all_required"])
        self.assertEqual(miss["group_coverage"], 0.5)
        either = query_rows([self.eval_set([["c", "d"]])], k=10, links_for=lambda s: [],
                            embedder_for=lambda s: None)[0]
        self.assertTrue(either["all_required"])

    def test_first_hit_credit_is_not_all_required(self):
        # The old reading: one required turn found, the other archived.
        eval_set = self.eval_set([["a"], ["b"]])
        eval_set["updates"] = [{"old": "b", "new": "d"}]
        row = query_rows([eval_set], k=10, links_for=lambda s: [], embedder_for=lambda s: None)[0]
        self.assertGreater(row["reciprocal_rank"], 0)
        self.assertFalse(row["all_required"])
        self.assertEqual(row["group_coverage"], 0.5)

    def test_sets_without_groups_have_no_new_fields_and_bad_groups_are_rejected(self):
        plain = self.eval_set([["a"]])
        del plain["queries"][0]["required_groups"]
        row = query_rows([plain], k=10, links_for=lambda s: [], embedder_for=lambda s: None)[0]
        self.assertNotIn("all_required", row)
        for bad in ([], [[]], [["a"], ["zz"]]):
            with self.assertRaises(ValueError):
                load_eval_set(self.eval_set(bad, relevant=["a"]))
        with self.assertRaises(ValueError):  # groups must cover exactly the relevant memories
            load_eval_set(self.eval_set([["a"]], relevant=["a", "b"]))

    def test_mean_rows_averages_the_new_fields(self):
        one = {"recall": 1.0, "reciprocal_rank": 1.0, "stale_first": None, "retrieved": [],
               "all_required": 1.0, "group_coverage": 1.0}
        two = dict(one, all_required=0.0, group_coverage=0.5)
        merged = evaluation.mean_rows([[one], [two]])[0]
        self.assertEqual((merged["all_required"], merged["group_coverage"]), (0.5, 0.75))


if __name__ == "__main__":
    unittest.main()
