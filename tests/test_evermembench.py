import copy
import hashlib
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from dynmemory.evermembench import FILE_HASHES, REVISION, load_topic, topic_memories
from dynmemory.store import MemoryStore

SCRIPT = Path(__file__).resolve().parents[1] / "experiments" / "evermembench_control.py"
spec = importlib.util.spec_from_file_location("evermembench_control", SCRIPT)
control = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = control
spec.loader.exec_module(control)


def message(number, text):
    return {"message_index": number, "speaker": "Ada", "dialogue": text,
            "time": "2025-01-01 09:00:00"}


DAY = {"topic_id": "01", "date": "2025-01-01", "dialogues": {
    "Group 1": [message(6, "six"), message(2, "two"), message(4, "four"),
                message(5, "five"), message(1, "one")],
    "Group 2": [message(2, "another two")],
    "Group 3": None,
}}
LATER = {"topic_id": "01", "date": "2025-01-02", "dialogues": {
    "Group 1": [dict(message(6, "a day later"), time="2025-01-02 09:00:00")],
}}
QUESTION = {"topic_id": "01", "id": "q1", "Q": "Who spoke?", "A": "answer-only",
            "R": [{"date": "2025-01-01", "group": "Group 1", "message_index": "1, 4-6"},
                  {"date": "2025-01-01", "group": "Group 2", "message_index": "2"}]}


class EverMemBenchTests(unittest.TestCase):
    def test_keys_retain_source_and_links_stay_within_a_day_and_group(self):
        data = topic_memories([LATER, DAY], [QUESTION])
        prefix = "2025-01-01|Group 1|"
        row = data["memories"][prefix + "6"]
        self.assertEqual((row["speaker"], row["channel"], row["time"], row["message_index"]),
                         ("Ada", "Group 1", "2025-01-01 09:00:00", 6))
        self.assertEqual(row["content"], "six")
        self.assertEqual([(link["source"], link["target"]) for link in data["links"]],
                         [(prefix + str(a), prefix + str(b))
                          for a, b in [(1, 2), (2, 4), (4, 5), (5, 6)]])
        query = data["queries"][0]
        expected = [[prefix + str(i) for i in [1, 4, 5, 6]], ["2025-01-01|Group 2|2"]]
        self.assertEqual(query["query"], QUESTION["Q"])
        self.assertEqual(query["required_groups"], expected)
        self.assertEqual(query["relevant"], expected[0] + expected[1])
        self.assertIn("cross_group", query["tags"])
        self.assertNotIn(QUESTION["A"], json.dumps(data))

    def test_rejects_a_missing_message_and_invalid_or_reversed_ranges(self):
        for value in ["1, 2-4", "0", "6-4", "4-6-8", "4,", "1000000000000000"]:
            with self.subTest(value=value):
                changed = copy.deepcopy(QUESTION)
                changed["R"][0]["message_index"] = value
                with self.assertRaisesRegex(ValueError, "q1"):
                    topic_memories([DAY], [changed])

    def test_rejects_mixed_topics_duplicate_coordinates_and_question_ids(self):
        for days, questions in [([DAY, dict(LATER, topic_id="02")], [QUESTION]),
                                ([DAY], [dict(QUESTION, topic_id="02")]),
                                ([DAY, DAY], [QUESTION]), ([DAY], [QUESTION, QUESTION])]:
            with self.assertRaises(ValueError):
                topic_memories(days, questions)
        changed = copy.deepcopy(DAY)
        changed["dialogues"]["Group 1"].append(message(1, "another one"))
        with self.assertRaisesRegex(ValueError, "duplicate message index"):
            topic_memories([changed], [QUESTION])

    def test_pinned_loader_rejects_modified_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            topic = Path(tmp) / "01"
            topic.mkdir()
            files = [topic / "dialogue.json", topic / "qa_01.json"]
            for path, value in zip(files, [[DAY], [QUESTION]]):
                path.write_text(json.dumps(value), encoding="utf-8")
            (Path(tmp) / "EverMemBench_QAR_1m.json").write_text("unrelated", encoding="utf-8")
            pin = tuple(hashlib.sha256(path.read_bytes()).hexdigest() for path in files)
            with patch.dict(FILE_HASHES, {"01": pin}):
                self.assertEqual(load_topic(Path(tmp), "01")["source"]["revision"], REVISION)
                files[1].write_bytes(files[1].read_bytes() + b" ")
                with self.assertRaisesRegex(ValueError, "SHA-256"):
                    load_topic(Path(tmp), "01")

    def test_public_lexical_search_recovers_each_group_in_a_separate_control(self):
        unchanged = copy.deepcopy(([DAY, LATER], [QUESTION]))
        over = dict(QUESTION, id="too-many", R=QUESTION["R"] * 5 + QUESTION["R"][:1])
        data, probes = control.prepare_control([DAY, LATER], [QUESTION, over])
        self.assertEqual(([DAY, LATER], [QUESTION]), unchanged)
        self.assertEqual(data["queries"][0]["query"], QUESTION["Q"])
        self.assertEqual(data["queries"][1]["query"], QUESTION["Q"])
        self.assertEqual(data["memories"]["2025-01-01|Group 1|6"]["content"], "six")
        measured = control.score_control(data, probes)
        self.assertEqual((measured["eligible"], measured["over_ten_entries"]), (1, 1))
        self.assertEqual(measured["all_required_at_10"], 1.0)
        self.assertEqual(measured["unplanted_token_hits"], 0)

    def test_wrong_message_on_another_day_fails_even_with_same_index_and_channel(self):
        data, probes = control.prepare_control([DAY, LATER], [QUESTION])
        probes[0].planted.remove(("2025-01-01", "Group 1", 6))
        probes[0].planted.add(("2025-01-02", "Group 1", 6))
        measured = control.score_control(data, probes)
        self.assertEqual(measured["all_required_at_10"], 0.0)
        self.assertEqual(measured["first_failed_ids"], ["q1"])
        self.assertFalse(measured["token_only_first_failure"]["all_required"])

    def test_failed_query_restores_every_marked_message_for_the_next_query(self):
        with MemoryStore(":memory:") as store:
            witnesses = [(store.add_memory(text, "episode").id, text)
                         for text in ("original a", "original b")]
            with self.assertRaisesRegex(RuntimeError, "interrupted"):
                with control.planted_fixture(store, witnesses, "uniquetoken"):
                    hits = store.search("uniquetoken", record_access=False)
                    self.assertEqual({hit.memory.id for hit in hits}, {mid for mid, _ in witnesses})
                    raise RuntimeError("interrupted")
            self.assertEqual(store.search("uniquetoken", record_access=False), [])
            self.assertEqual([store.get_memory(mid).content for mid, _ in witnesses],
                             ["original a", "original b"])

    def test_independent_source_intervals_catch_an_incorrect_converter_group(self):
        data, probes = control.prepare_control([DAY], [QUESTION])
        data["queries"][0]["required_groups"][0].remove("2025-01-01|Group 1|5")
        with self.assertRaisesRegex(ValueError, "differ from source intervals"):
            control.score_control(data, probes)

    def test_question_terms_displace_the_witness_under_the_original_rule_only(self):
        # Why the rule changed on 2026-11-26: the appended token loses to question words.
        day = copy.deepcopy(DAY)
        day["dialogues"]["Group 3"] = [
            message(n, "raven amber violet signal") for n in range(1, 12)
        ]
        day["dialogues"]["Group 1"][0]["dialogue"] = "word " * 400
        query = dict(QUESTION, Q="raven amber violet signal " * 5)
        data, probes = control.prepare_control([day], [query])
        original = control.score_control(data, probes, rule="original")
        self.assertEqual(original["all_required_at_10"], 0.0)
        self.assertEqual(original["token_only_first_failure"],
                         {"question_id": "q1", "exact_planted_set": True, "all_required": True})
        token_only = control.score_control(data, probes)
        self.assertEqual(token_only["all_required_at_10"], 1.0)
        self.assertEqual(token_only["unplanted_token_hits"], 0)

    def test_off_by_one_fault_plants_the_next_message_and_fails_the_rule(self):
        single = dict(QUESTION, id="single",
                      R=[{"date": "2025-01-01", "group": "Group 1", "message_index": "1"}])
        data, probes = control.prepare_control([DAY], [single])
        self.assertEqual(probes[0].planted, {("2025-01-01", "Group 1", 1)})
        self.assertEqual(control.score_control(data, probes)["all_required_at_10"], 1.0)
        data, probes = control.prepare_control([DAY], [single], fault="off-by-one")
        self.assertEqual(probes[0].planted, {("2025-01-01", "Group 1", 2)})
        faulty = control.score_control(data, probes)
        self.assertEqual(faulty["all_required_at_10"], 0.0)
        self.assertEqual(faulty["unplanted_token_hits"], 0)
        # The last message of a group has no successor, so its witness is dropped.
        data, probes = control.prepare_control([DAY], [QUESTION], fault="off-by-one")
        self.assertEqual(probes[0].planted, set())
        self.assertEqual(control.score_control(data, probes)["all_required_at_10"], 0.0)

    def test_unknown_rule_and_fault_are_rejected(self):
        data, probes = control.prepare_control([DAY], [QUESTION])
        with self.assertRaises(ValueError):
            control.score_control(data, probes, rule="question-only")
        with self.assertRaises(ValueError):
            control.prepare_control([DAY], [QUESTION], fault="shuffle")

    def test_main_writes_both_reports_and_detects_the_fault(self):
        with tempfile.TemporaryDirectory() as tmp:
            topic = Path(tmp) / "01"
            topic.mkdir()
            files = [topic / "dialogue.json", topic / "qa_01.json"]
            for path, value in zip(files, [[DAY, LATER], [QUESTION]]):
                path.write_text(json.dumps(value), encoding="utf-8")
            pin = tuple(hashlib.sha256(path.read_bytes()).hexdigest() for path in files)
            output = Path(tmp) / "report.json"
            with patch.dict(FILE_HASHES, {"01": pin}):
                code = control.main(["--data", tmp, "--topic", "01", "--output", str(output)])
                report = json.loads(output.read_text())
                markdown = output.with_suffix(".md").read_text()
                self.assertEqual((code, report["rule"], report["passed"]), (0, "token-only", True))
                self.assertEqual(report["deviation"]["run1"]["all_required_hits"], 117)
                self.assertIn("**Passed**", markdown)
                code = control.main(["--data", tmp, "--topic", "01", "--fault", "off-by-one",
                                     "--output", str(output)])
                report = json.loads(output.read_text())
                self.assertEqual((code, report["passed"], report["fault_detected"]), (0, False, True))
                self.assertIn("**Fault detected**", output.with_suffix(".md").read_text())
