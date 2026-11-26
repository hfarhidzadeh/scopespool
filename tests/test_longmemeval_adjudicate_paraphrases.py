import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile


SCRIPT = Path(__file__).resolve().parents[1] / "experiments" / "longmemeval_adjudicate_paraphrases.py"
spec = importlib.util.spec_from_file_location("longmemeval_adjudicate_paraphrases", SCRIPT)
adjudication = importlib.util.module_from_spec(spec)
spec.loader.exec_module(adjudication)


def judgment(relation="equivalent", usable=True, rationale="Same claim", notes=None):
    return dict(relation=relation, usable=usable, rationale=rationale, notes=notes)


class ParaphraseAdjudicationTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.packet = self.root / "packet.zip"
        with ZipFile(self.packet, "w") as packet:
            packet.writestr("claim_pairs.md", "Test fixture for three cases.")
        self.manifest = {
            "format_version": 1,
            "data_sha256": "a" * 64,
            "reviewer_zip_sha256": adjudication.sha256(self.packet.read_bytes()),
            "source_family_counts": {"alpha": 2, "beta": 1},
            "cases": {
                "P001": dict(source_family="alpha", source_question="q1", source_session="s1"),
                "P002": dict(source_family="alpha", source_question="q1", source_session="s1"),
                "P003": dict(source_family="beta", source_question="q2", source_session="s2"),
            },
        }

    def write(self, name, data):
        path = self.root / name
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    def compare(self, left=None, right=None, reviewer_b="Reviewer B", split=None):
        valid = {case_id: judgment() for case_id in self.manifest["cases"]}
        manifest = self.write("manifest.json", self.manifest)
        ballot_a = self.write("a.json", dict(reviewer="Reviewer A", cases=valid if left is None else left))
        ballot_b = self.write("b.json", dict(reviewer=reviewer_b, cases=valid if right is None else right))
        split_path = None if split is None else self.write("split.json", split)
        return adjudication.make_worksheet(manifest, self.packet, ballot_a, ballot_b, split_path)

    def test_compares_open_and_unusable_separately_with_blank_adjudication(self):
        left = {
            "P001": judgment(),
            "P002": judgment("open", rationale="Time is unclear"),
            "P003": judgment(None, False, "Truncated excerpt"),
        }
        right = {case_id: judgment() for case_id in left}
        result = self.compare(left, right)
        self.assertEqual(result["status"], "manual_adjudication_required")
        self.assertEqual(result["summary"]["comparisons"], {
            "usability": dict(match=2, differ=1, not_comparable=0),
            "relation": dict(match=1, differ=1, not_comparable=1),
        })
        self.assertEqual(result["summary"]["reviewer_judgments"][0],
                         dict(equivalent=1, incompatible=0, distinct_compatible=0, open=1, unusable=1))
        self.assertEqual(result["by_source_family"]["alpha"]["cases_compared"], 2)
        self.assertIn("open_judgment", result["cases"]["P002"]["attention_flags"])
        self.assertIn("unusable_judgment", result["cases"]["P003"]["attention_flags"])
        self.assertTrue(all(value is None for row in result["cases"].values()
                            for value in row["manual_adjudication"].values()))

    def test_distinct_reviewers_and_exact_case_set_required(self):
        partial = {"P001": judgment(), "P004": judgment()}
        with self.assertRaisesRegex(ValueError, "missing case IDs: P002, P003") as error:
            self.compare(left=partial)
        self.assertIn("unknown case IDs: P004", str(error.exception))
        with self.assertRaisesRegex(ValueError, "distinct reviewer identifiers"):
            self.compare(reviewer_b=" reviewer a ")

    def test_labels_usability_and_rationales_follow_the_rubric(self):
        invalid = [
            (judgment("uncertain"), "require a relation"),
            (judgment("open", False), "require a null relation"),
            (judgment(None, None, None), "usable must be true or false"),
            (judgment(usable=1), "usable must be true or false"),
            (judgment(None, False, ""), "rationale must be nonempty"),
        ]
        for row, error in invalid:
            with self.subTest(judgment=row), self.assertRaisesRegex(ValueError, error):
                self.compare(left=dict(P001=row, P002=judgment(), P003=judgment()))

    def test_rejects_manifest_from_another_packet(self):
        self.manifest["reviewer_zip_sha256"] = "b" * 64
        with self.assertRaisesRegex(ValueError, "ZIP hash does not match"):
            self.compare()

    def test_checks_whole_family_split_and_overlapping_sessions(self):
        split = dict(alpha="development", beta="holdout")
        report = self.compare(split=split)
        self.assertEqual(report["family_split"], split)
        self.assertTrue(report["source"]["family_split_sha256"])
        with self.assertRaisesRegex(ValueError, "assign exactly the manifest"):
            self.compare(split=dict(alpha="development"))
        with self.assertRaisesRegex(ValueError, "with both present"):
            self.compare(split=dict(alpha="holdout", beta="holdout"))
        self.manifest["cases"]["P003"]["source_session"] = "s1"
        with self.assertRaisesRegex(ValueError, "source_session 's1' in both splits"):
            self.compare(split=split)

    def test_rejects_duplicate_case_keys_in_json(self):
        path = self.root / "duplicate.json"
        path.write_text('{"cases": {"P001": {}, "P001": {}}}', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "duplicate key 'P001'"):
            adjudication.read_json(path)


if __name__ == "__main__":
    unittest.main()
