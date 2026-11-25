import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "experiments" / "longmemeval_adjudicate_ballots.py"
spec = importlib.util.spec_from_file_location("longmemeval_adjudicate_ballots", SCRIPT)
adjudication = importlib.util.module_from_spec(spec)
spec.loader.exec_module(adjudication)


def judgment(**overrides):
    return dict(
        dict(answer="One turn", evidence_status="supported",
             required_evidence_groups=[["a:0", "a:2"], ["b:0"]], relation_status="labelled",
             relations=[dict(old="a:0", new="b:0", relation="supersedes", rationale="Same fact")],
             notes=None),
        **overrides,
    )


class AdjudicationTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.manifest = self.write("manifest.json", {
            "format_version": 1, "data_sha256": "a" * 64, "annotations_sha256": "b" * 64,
            "cases": {
                "E001": dict(question_id="source-1", priority_batch="older_required_overlap",
                             shown_user_turn_ids=["a:0", "a:2", "b:0"]),
                "E002": dict(question_id="source-2", priority_batch="remaining",
                             shown_user_turn_ids=["c:0", "c:2"]),
            },
        })

    def write(self, name, document):
        path = self.root / name
        path.write_text(json.dumps(document), encoding="utf-8")
        return path

    def compare(self, left, right, batch="older_required_overlap", reviewer_b="Review-B"):
        first = self.write("a.json", dict(reviewer="Review-A", cases=left))
        second = self.write("b.json", dict(reviewer=reviewer_b, cases=right))
        return adjudication.make_worksheet(self.manifest, first, second, batch)

    def test_identical_evidence_and_relations_match_without_becoming_adjudicated(self):
        report = self.compare(
            {"E001": judgment()},
            {"E001": judgment(
                answer="One  turn", required_evidence_groups=[["b:0"], ["a:2", "a:0"]],
                relations=[dict(old="a:0", new="b:0", relation="supersedes", rationale="Update")],
            )},
        )
        self.assertEqual(report["status"], "manual_adjudication_required")
        self.assertEqual(report["cases"]["E001"]["question_id"], "source-1")
        self.assertTrue(all(report["cases"]["E001"]["comparisons"].values()))
        self.assertEqual(report["summary"]["cases_flagged"], 0)
        self.assertIsNone(report["cases"]["E001"]["manual_adjudication"]["disposition"])

    def test_uncertain_evidence_does_not_hide_a_definite_relation_disagreement(self):
        report = self.compare(
            {"E001": judgment()},
            {"E001": judgment(answer=None, evidence_status="uncertain", required_evidence_groups=[],
                              relation_status="no_relation", relations=[], notes="Date unclear")},
        )
        comparisons = report["summary"]["comparisons"]
        self.assertEqual(comparisons["required_evidence_groups"]["not_comparable"], 1)
        self.assertEqual(comparisons["relation_edges"]["differ"], 1)
        self.assertIn("uncertain_judgment", report["cases"]["E001"]["attention_flags"])
        self.assertIn("answer_present_in_one_ballot", report["cases"]["E001"]["attention_flags"])

    def test_rejects_invalid_references_empty_judgments_and_bad_relation_structure(self):
        valid = {"E001": judgment()}
        examples = [
            (judgment(required_evidence_groups=[["c:0"]]), "not a listed user turn"),
            (judgment(relations=[dict(old="a:0", new="c:0", relation="supersedes",
                                      rationale="Unknown new turn")]), "not a listed user turn"),
            (judgment(relations=[dict(old="a:0", new="a:0", relation="independent",
                                      rationale="Same turn")]), "different turns"),
            (judgment(relations=[dict(old="a:0", new="b:0", relation="supersedes")]),
             "needs a rationale"),
            (judgment(evidence_status="uncertain", required_evidence_groups=[]),
             "require explanatory notes"),
            (dict(evidence_status=None, relation_status=None), "incomplete or invalid ballot"),
        ]
        for invalid, error in examples:
            with self.subTest(error=error):
                with self.assertRaisesRegex(ValueError, error):
                    self.compare(valid, {"E001": invalid})

    def test_full_scope_rejects_missing_cases_and_duplicate_reviewer(self):
        partial = {"E001": judgment()}
        with self.assertRaisesRegex(ValueError, "E002: missing case judgment"):
            self.compare(partial, partial, batch=None)
        with self.assertRaisesRegex(ValueError, "distinct reviewer identifiers"):
            self.compare(partial, partial, reviewer_b="review-a")

    def test_duplicate_keys_are_rejected_before_comparison(self):
        path = self.root / "duplicate.json"
        path.write_text('{"cases": {"E001": {}, "E001": {}}}', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "duplicate key 'E001'"):
            adjudication.read_json(path)


if __name__ == "__main__":
    unittest.main()
