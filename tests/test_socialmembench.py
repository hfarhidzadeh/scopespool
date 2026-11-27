import base64
import copy
import hashlib
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from dynmemory.socialmembench import (FILE_HASHES, REVISION, build_networks, load_networks,
                                      read_parquet, read_release, snappy_decompress)
from dynmemory.store import MemoryStore

SCRIPT = Path(__file__).resolve().parents[1] / "experiments" / "socialmembench_control.py"
spec = importlib.util.spec_from_file_location("socialmembench_control", SCRIPT)
control = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = control
spec.loader.exec_module(control)

# Synthetic Parquet files written by pyarrow 17.0.0 (store_schema=False). The
# five-row table has optional string, int64, double and boolean columns with
# nulls, plus a required int32 column. NESTED holds a list column and ZSTD a
# zstd-compressed column; the reader must reject both.
V1_SNAPPY_DICT = (
    "UEFSMRUEFTgVPEwVBhUAEgAAHGwDAAAAYWRhAgAAAGJvCwAAAMOpbWlsZSDwn5iAFQAVFBUYLBUKFRAVBhUGHDYC"
    "KAvDqW1pbGUg8J+YgBgDYWRhAAAACiQCAAAAAx0CA4QAJsYBHBUMGTUABhAZGARuYW1lFQIWCha2ARa+ASZgJggc"
    "NgIoC8OpbWlsZSDwn5iAGANhZGEAGSwVBBUAFQIAFQAVEBUCAAAAFQQVQBU4TBUIFQASAAAgBAEACQEAAgkHQAD8"
    "/////////wAAAAAAAQAAFQAVFBUYLBUKFRAVBhUGHBgIAAAAAAABAAAYCPz/////////FgIoCAAAAAAAAQAAGAj8"
    "/////////wAAAAokAgAAAAMbAgPkACa8BBwVBBk1AAYQGRgBbhUCFgoW6gEW5gEmqgMm1gIcGAgAAAAAAAEAABgI"
    "/P////////8WAigIAAAAAAABAAAYCPz/////////ABksFQQVABUCABUAFRAVAgAAABUEFUAVNkwVCBUAEgAAIAAA"
    "BQEE4D8FBwgAAkAJCCTwvwAAAAAAAAhAFQAVFBUYLBUKFRAVBhUGHBgIAAAAAAAACEAYCAAAAAAAAPC/FgIoCAAA"
    "AAAAAAhAGAgAAAAAAADwvwAAAAokAgAAAAMdAgPkACbaBxwVChk1AAYQGRgBeBUCFgoW6gEW5AEmyAYm9gUcGAgA"
    "AAAAAAAIQBgIAAAAAAAA8L8WAigIAAAAAAAACEAYCAAAAAAAAPC/ABksFQQVABUCABUAFRAVAgAAABUAFQ4VEiwV"
    "ChUAFQYVBhwYAQEYAQAWAigBARgBAAAAAAcYAgAAAAMbBSboCRwVABklBgAZGARmbGFnFQIWChZQFlQmlAk8GAEB"
    "GAEAFgIoAQEYAQAAGRwVABUAFQIAAAAVBBUoFSxMFQoVABIAABRMBwAAAAgAAAAJAAAACgAAAAsAAAAVABUWFRos"
    "FQoVEBUGFQYcGAQLAAAAGAQHAAAAFgAoBAsAAAAYBAcAAAAAAAALKAIAAAAKAQMDiEYAJpIMHBUCGTUABhAZGAVz"
    "bWFsbBUCFgoWtAEWvAEmngsm1gocGAQLAAAAGAQHAAAAFgAoBAsAAAAYBAcAAAAAGSwVBBUAFQIAFQAVEBUCAAAA"
    "FQQZbDUAGAZzY2hlbWEVCgAVDCUCGARuYW1lJQBMHAAAABUEJQIYAW4AFQolAhgBeAAVACUCGARmbGFnABUCJQIY"
    "BXNtYWxsABYKGRwZXCbGARwVDBk1AAYQGRgEbmFtZRUCFgoWtgEWvgEmYCYIHDYCKAvDqW1pbGUg8J+YgBgDYWRh"
    "ABksFQQVABUCABUAFRAVAgAAACa8BBwVBBk1AAYQGRgBbhUCFgoW6gEW5gEmqgMm1gIcGAgAAAAAAAEAABgI/P//"
    "//////8WAigIAAAAAAABAAAYCPz/////////ABksFQQVABUCABUAFRAVAgAAACbaBxwVChk1AAYQGRgBeBUCFgoW"
    "6gEW5AEmyAYm9gUcGAgAAAAAAAAIQBgIAAAAAAAA8L8WAigIAAAAAAAACEAYCAAAAAAAAPC/ABksFQQVABUCABUA"
    "FRAVAgAAACboCRwVABklBgAZGARmbGFnFQIWChZQFlQmlAk8GAEBGAEAFgIoAQEYAQAAGRwVABUAFQIAAAAmkgwc"
    "FQIZNQAGEBkYBXNtYWxsFQIWCha0ARa8ASaeCybWChwYBAsAAAAYBAcAAAAWACgECwAAABgEBwAAAAAZLBUEFQAV"
    "AgAVABUQFQIAAAAWjgcWCiYIFpgHFAAAKCBwYXJxdWV0LWNwcC1hcnJvdyB2ZXJzaW9uIDE3LjAuMBlcHAAAHAAA"
    "HAAAHAAAHAAAABoCAABQQVIx"
)
V2_PLAIN_UNCOMPRESSED = (
    "UEFSMRUGFUoVSlwVChUCFQoVABUEFQASHDYCKAvDqW1pbGUg8J+YgBgDYWRhAAAAAx0DAAAAYWRhAgAAAGJvAwAA"
    "AGFkYQsAAADDqW1pbGUg8J+YgCaqARwVDBklBgAZGARuYW1lFQAWChaiARaiASYIPDYCKAvDqW1pbGUg8J+YgBgD"
    "YWRhABkcFQAVABUCAAAAFQYVRBVEXBUKFQIVChUAFQQVABIcGAgAAAAAAAEAABgI/P////////8WAigIAAAAAAAB"
    "AAAYCPz/////////AAAAAxsBAAAAAAAAAAIAAAAAAAAA/P////////8AAAAAAAEAACbuAxwVBBklBgAZGAFuFQAW"
    "ChbIARbIASamAjwYCAAAAAAAAQAAGAj8/////////xYCKAgAAAAAAAEAABgI/P////////8AGRwVABUAFQIAAAAV"
    "BhVEFURcFQoVAhUKFQAVBBUAEhwYCAAAAAAAAAhAGAgAAAAAAADwvxYCKAgAAAAAAAAIQBgIAAAAAAAA8L8AAAAD"
    "HQAAAAAAAOA/AAAAAAAAAkAAAAAAAADwvwAAAAAAAAhAJtoGHBUKGSUGABkYAXgVABYKFsgBFsgBJpIFPBgIAAAA"
    "AAAACEAYCAAAAAAAAPC/FgIoCAAAAAAAAAhAGAgAAAAAAADwvwAZHBUAFQAVAgAAABUGFRAVEFwVChUCFQoVBhUE"
    "FQASHBgBARgBABYCKAEBGAEAAAAAAxsCAAAAAwUm2ggcFQAZFQYZGARmbGFnFQAWChZcFlwm/gc8GAEBGAEAFgIo"
    "AQEYAQAAGRwVABUGFQIAAAAVBhUsFSxcFQoVABUKFQAVBBUAEhwYBAsAAAAYBAcAAAAWACgECwAAABgEBwAAAAAA"
    "AAoBBwAAAAgAAAAJAAAACgAAAAsAAAAm1gocFQIZJQYAGRgFc21hbGwVABYKFpABFpABJsYJPBgECwAAABgEBwAA"
    "ABYAKAQLAAAAGAQHAAAAABkcFQAVABUCAAAAFQQZbDUAGAZzY2hlbWEVCgAVDCUCGARuYW1lJQBMHAAAABUEJQIY"
    "AW4AFQolAhgBeAAVACUCGARmbGFnABUCJQIYBXNtYWxsABYKGRwZXCaqARwVDBklBgAZGARuYW1lFQAWChaiARai"
    "ASYIPDYCKAvDqW1pbGUg8J+YgBgDYWRhABkcFQAVABUCAAAAJu4DHBUEGSUGABkYAW4VABYKFsgBFsgBJqYCPBgI"
    "AAAAAAABAAAYCPz/////////FgIoCAAAAAAAAQAAGAj8/////////wAZHBUAFQAVAgAAACbaBhwVChklBgAZGAF4"
    "FQAWChbIARbIASaSBTwYCAAAAAAAAAhAGAgAAAAAAADwvxYCKAgAAAAAAAAIQBgIAAAAAAAA8L8AGRwVABUAFQIA"
    "AAAm2ggcFQAZFQYZGARmbGFnFQAWChZcFlwm/gc8GAEBGAEAFgIoAQEYAQAAGRwVABUGFQIAAAAm1gocFQIZJQYA"
    "GRgFc21hbGwVABYKFpABFpABJsYJPBgECwAAABgEBwAAABYAKAQLAAAAGAQHAAAAABkcFQAVABUCAAAAFp4GFgom"
    "CBaeBhQAACggcGFycXVldC1jcHAtYXJyb3cgdmVyc2lvbiAxNy4wLjAZXBwAABwAABwAABwAABwAAADuAQAAUEFS"
    "MQ=="
)
NESTED = (
    "UEFSMRUEFTAVMEwVBhUAEgAAAQAAAAAAAAACAAAAAAAAAAMAAAAAAAAAFQAVIBUgLBUGFRAVBhUGHBgIAwAAAAAA"
    "AAAYCAEAAAAAAAAAFgAoCAMAAAAAAAAAGAgBAAAAAAAAAAAAAAIAAAADAgIAAAAGAwIDJAAm7gEcFQQZNQAGEBk4"
    "AnhzBGxpc3QHZWxlbWVudBUAFgYW5gEW5gEmVCYIHBgIAwAAAAAAAAAYCAEAAAAAAAAAFgAoCAMAAAAAAAAAGAgB"
    "AAAAAAAAAAAZLBUEFQAVAgAVABUQFQIAAAAVBBlMNQAYBnNjaGVtYRUCADUCGAJ4cxUCFQZMPAAAADUEGARsaXN0"
    "FQIAFQQlAhgHZWxlbWVudAAWBBkcGRwm7gEcFQQZNQAGEBk4AnhzBGxpc3QHZWxlbWVudBUAFgYW5gEW5gEmVCYI"
    "HBgIAwAAAAAAAAAYCAEAAAAAAAAAFgAoCAMAAAAAAAAAGAgBAAAAAAAAAAAZLBUEFQAVAgAVABUQFQIAAAAW5gEW"
    "BCYIFuYBFAAAKCBwYXJxdWV0LWNwcC1hcnJvdyB2ZXJzaW9uIDE3LjAuMBkcHAAAAN0AAABQQVIx"
)
ZSTD = (
    "UEFSMRUEFRAVIkwVAhUAEgAAKLUv/SAIQQAAAQAAAAAAAAAVABUSFSQsFQIVEBUGFQYcGAgBAAAAAAAAABgIAQAA"
    "AAAAAAAWACgIAQAAAAAAAAAYCAEAAAAAAAAAAAAAKLUv/SAJSQAAAgAAAAIBAQIAJuQBHBUEGTUABhAZGAFuFQwW"
    "Aha4ARbcASZGJggcGAgBAAAAAAAAABgIAQAAAAAAAAAWACgIAQAAAAAAAAAYCAEAAAAAAAAAABksFQQVABUCABUA"
    "FRAVAgAAABUEGSw1ABgGc2NoZW1hFQIAFQQlAhgBbgAWAhkcGRwm5AEcFQQZNQAGEBkYAW4VDBYCFrgBFtwBJkYm"
    "CBwYCAEAAAAAAAAAGAgBAAAAAAAAABYAKAgBAAAAAAAAABgIAQAAAAAAAAAAGSwVBBUAFQIAFQAVEBUCAAAAFrgB"
    "FgImCBbcARQAACggcGFycXVldC1jcHAtYXJyb3cgdmVyc2lvbiAxNy4wLjAZHBwAAACvAAAAUEFSMQ=="
)


def fixture_bytes(parts):
    return base64.b64decode("".join(parts))


def turn(net, session, index, turn_id, speaker, text, reply=""):
    return {"network_id": net, "session_id": f"{net}_s{session:02d}", "session_index": session,
            "session_topic": "topic", "session_date_label": "label",
            "session_date": f"2025-01-{session:02d}", "session_gap_days": 0,
            "active_participants_json": "[]", "corpus_start_date": "2025-01-01",
            "turn_id": turn_id, "speaker_persona_id": "p_" + speaker.lower(),
            "speaker_display_name": speaker, "timestamp_label": "t",
            "timestamp": f"2025-01-{session:02d}T09:{index:02d}:00", "message": text,
            "message_index": index, "reply_to_turn_id": reply}


def anchor(turn_id, excerpt, speaker, session):
    return {"session_index": session, "turn_id": turn_id, "speaker_display_name": speaker,
            "message_excerpt": excerpt, "relevance": "why"}


def question(net, qid, anchors, text="What does Ada prefer?"):
    return {"qa_id": qid, "network_id": net, "query_type": "Q1", "difficulty": "easy",
            "question": text, "answer": "answer-only text", "answer_format": "short_answer",
            "options_json": "[]", "correct_option": "", "contamination_foil": "",
            "evidence_anchors_json": json.dumps(anchors), "temporal_anchors_json": "[]",
            "qc_phase1_score": 1.0, "qc_phase2_grounded": True, "qc_phase3_flagged": False,
            "source_challenge_id": "ch", "generation_seed": 1, "metadata_json": "{}"}


# Network A: session 1 numbers turn IDs from t000 (suffix = index - 1); session 2
# from t001 (suffix = index), as 1,315 released turns do. Network B reuses qa_id q1.
CONVERSATIONS = [
    turn("grp_a", 1, 1, "grp_a_s01_t000", "Ada", "I always order the mushroom risotto"),
    turn("grp_a", 1, 2, "grp_a_s01_t001", "Bo", "Count me out of karaoke night", "grp_a_s01_t000"),
    turn("grp_a", 1, 3, "grp_a_s01_t002", "Ada", "Lighthouse walk on Sunday works"),
    turn("grp_a", 2, 1, "grp_a_s02_t001", "Bo", "Back from the mountains finally"),
    turn("grp_a", 2, 2, "grp_a_s02_t002", "Ada", "Actually I switched to sushi lately"),
    turn("grp_a", 2, 3, "grp_a_s02_t003", "Cy", "Welcome back everyone"),
    turn("grp_b", 1, 2, "grp_b_s01_t001", "Di", "Chess club moved to Tuesdays"),
    turn("grp_b", 1, 1, "grp_b_s01_t000", "Ed", "Who brings the clocks"),
]
QA = [
    question("grp_a", "q1", [anchor("grp_a_s01_t000", "mushroom risotto", "Ada", 1),
                             anchor("grp_a_s02_t002", "switched to sushi", "Ada", 2)]),
    question("grp_a", "q2", [anchor("grp_a_s01_t001", "out of karaoke", "Bo", 1),
                             anchor("grp_a_s01_t001", "karaoke night", "Bo", 1)]),
    question("grp_b", "q1", [anchor("grp_b_s01_t001", "moved to Tuesdays", "Di", 1)]),
]


class ParquetReaderTests(unittest.TestCase):
    EXPECTED = [
        {"name": "ada", "n": 1, "x": 0.5, "flag": True, "small": 7},
        {"name": None, "n": 2, "x": None, "flag": False, "small": 8},
        {"name": "bo", "n": None, "x": 2.25, "flag": None, "small": 9},
        {"name": "ada", "n": -4, "x": -1.0, "flag": True, "small": 10},
        {"name": "émile \U0001f600", "n": 2 ** 40, "x": 3.0, "flag": False, "small": 11},
    ]

    def read(self, parts):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "f.parquet"
            path.write_bytes(fixture_bytes(parts))
            return read_parquet(path)

    def test_reads_snappy_dictionary_v1_and_plain_uncompressed_v2_pages(self):
        for parts in (V1_SNAPPY_DICT, V2_PLAIN_UNCOMPRESSED):
            rows = self.read(parts)
            self.assertEqual(rows, self.EXPECTED)
            self.assertEqual([type(v) for v in rows[0].values()], [str, int, float, bool, int])

    def test_rejects_nested_columns_unsupported_codecs_and_other_files(self):
        with self.assertRaisesRegex(ValueError, "nested"):
            self.read(NESTED)
        with self.assertRaisesRegex(ValueError, "codec"):
            self.read(ZSTD)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "f.parquet"
            path.write_bytes(b"not parquet at all")
            with self.assertRaisesRegex(ValueError, "not a Parquet file"):
                read_parquet(path)
            raw = bytearray(fixture_bytes(V1_SNAPPY_DICT))
            path.write_bytes(bytes(raw[:200]) + bytes(raw[-8:]))
            with self.assertRaises((ValueError, IndexError)):
                read_parquet(path)

    def test_snappy_overlapping_copy_and_invalid_offsets(self):
        # Literal "ab", then copy 8 bytes from offset 2: the copy overlaps its own output.
        self.assertEqual(snappy_decompress(bytes([10, 0x04]) + b"ab" + bytes([0x11, 2])),
                         b"ababababab")
        with self.assertRaisesRegex(ValueError, "offset"):
            snappy_decompress(bytes([10, 0x04]) + b"ab" + bytes([0x11, 3]))
        with self.assertRaisesRegex(ValueError, "length"):
            snappy_decompress(bytes([9, 0x04]) + b"ab" + bytes([0x11, 2]))


class LoaderTests(unittest.TestCase):
    def test_turn_ids_are_keys_and_turn_fields_survive(self):
        suites = build_networks(CONVERSATIONS, QA)
        self.assertEqual([s["id"] for s in suites], ["grp_a", "grp_b"])
        a = suites[0]
        row = a["memories"]["grp_a_s02_t002"]
        self.assertEqual((row["content"], row["speaker"], row["speaker_id"], row["session_index"],
                          row["message_index"], row["time"], row["channel"]),
                         ("Actually I switched to sushi lately", "Ada", "p_ada", 2, 2,
                          "2025-01-02T09:02:00", "grp_a"))
        self.assertEqual(a["memories"]["grp_a_s01_t001"]["reply_to"], "grp_a_s01_t000")
        self.assertIsNone(a["memories"]["grp_a_s01_t000"]["reply_to"])
        # Links join consecutive turns within a session, never across sessions.
        self.assertEqual([(l["source"][-8:], l["target"][-8:]) for l in a["links"]],
                         [("s01_t000", "s01_t001"), ("s01_t001", "s01_t002"),
                          ("s02_t001", "s02_t002"), ("s02_t002", "s02_t003")])
        q1, q2 = a["queries"]
        self.assertEqual(q1["query"], "What does Ada prefer?")
        self.assertEqual(q1["required_groups"], [["grp_a_s01_t000"], ["grp_a_s02_t002"]])
        self.assertEqual([e["excerpt"] for e in q1["evidence"]], ["mushroom risotto", "switched to sushi"])
        self.assertIn("cross_session", q1["tags"])
        # Two anchors on one turn form one required group but keep both excerpts.
        self.assertEqual(q2["relevant"], ["grp_a_s01_t001"])
        self.assertEqual(len(q2["evidence"]), 2)
        self.assertIn("single_session", q2["tags"])
        self.assertEqual(suites[1]["queries"][0]["id"], "q1")
        # Ordering within a network follows session and message index, not row order.
        self.assertEqual(list(suites[1]["memories"]), ["grp_b_s01_t000", "grp_b_s01_t001"])
        self.assertNotIn("answer-only", json.dumps(suites))

    def test_rejects_unresolved_foreign_or_duplicate_references(self):
        bad_anchor = question("grp_a", "q9", [anchor("grp_a_s09_t000", "x", "Ada", 9)])
        foreign = question("grp_a", "q9", [anchor("grp_b_s01_t000", "Who", "Ed", 1)])
        for qa, pattern in [([bad_anchor], "q9"), ([foreign], "q9"), ([QA[0], QA[0]], "duplicate"),
                            ([dict(QA[0], evidence_anchors_json="[]")], "q1")]:
            with self.subTest(pattern=pattern):
                with self.assertRaisesRegex(ValueError, pattern):
                    build_networks(CONVERSATIONS, qa)
        with self.assertRaisesRegex(ValueError, "duplicate turn_id"):
            build_networks(CONVERSATIONS + [CONVERSATIONS[0]], QA)
        clash = dict(CONVERSATIONS[0], turn_id="grp_a_s01_other")
        with self.assertRaisesRegex(ValueError, "duplicate message index"):
            build_networks(CONVERSATIONS + [clash], QA)
        with self.assertRaisesRegex(ValueError, "networks without turns"):
            build_networks(CONVERSATIONS, QA + [question("grp_z", "q1", [])])
        with self.assertRaisesRegex(ValueError, "message"):
            build_networks([dict(CONVERSATIONS[0], message="  ")] + CONVERSATIONS[1:], QA)

    def test_read_release_checks_pinned_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "qa.parquet"
            raw = fixture_bytes(V1_SNAPPY_DICT)
            path.write_bytes(raw)
            pin = hashlib.sha256(raw).hexdigest()
            with patch.dict(FILE_HASHES, {"qa.parquet": pin}):
                tables = read_release(Path(tmp), names=("qa.parquet",))
                self.assertEqual(len(tables["qa"]), 5)
                path.write_bytes(raw + b"\0")
                with self.assertRaisesRegex(ValueError, "SHA-256"):
                    read_release(Path(tmp), names=("qa.parquet",))
                path.write_bytes(fixture_bytes(V2_PLAIN_UNCOMPRESSED))
                self.assertEqual(len(read_release(Path(tmp), verify=False,
                                                  names=("qa.parquet",))["qa"]), 5)
            with self.assertRaisesRegex(ValueError, "unknown"):
                read_release(Path(tmp), names=("other.parquet",))

    def test_load_networks_records_the_revision_only_when_verified(self):
        tables = {"conversations": CONVERSATIONS, "qa": QA}
        with patch("dynmemory.socialmembench.read_release", return_value=tables):
            self.assertEqual(load_networks(Path("."))[0]["source"]["revision"], REVISION)
            self.assertIsNone(load_networks(Path("."), verify=False)[0]["source"]["revision"])


class ControlTests(unittest.TestCase):
    def test_control_passes_on_correct_keys_and_leaves_inputs_unchanged(self):
        before = copy.deepcopy((CONVERSATIONS, QA))
        result = control.run_control(CONVERSATIONS, QA)
        self.assertEqual(before, (CONVERSATIONS, QA))
        t = result["totals"]
        self.assertTrue(result["passed"])
        self.assertEqual((t["networks"], t["questions"], t["anchors"], t["key_roundtrip"],
                          t["excerpt_verbatim"], t["canary_passed"], t["unplanted_token_hits"]),
                         (2, 3, 5, 5, 5, 3, 0))

    def test_off_by_one_fault_fails_every_question(self):
        result = control.run_control(CONVERSATIONS, QA, fault="off-by-one")
        t = result["totals"]
        self.assertFalse(result["passed"])
        self.assertEqual((t["key_roundtrip"], t["excerpt_verbatim"], t["canary_passed"]), (0, 0, 0))

    def test_turn_suffix_fault_fails_only_where_suffix_and_index_disagree(self):
        result = control.run_control(CONVERSATIONS, QA, fault="turn-suffix")
        t = result["totals"]
        self.assertFalse(result["passed"])
        # Only grp_a q1's session-2 anchor is misread (t002 is index 2, not 3).
        self.assertEqual((t["key_roundtrip"], t["canary_passed"]), (4, 2))
        failed = {(r["network"], tuple(r["first_failed_ids"])) for r in result["networks"]}
        self.assertEqual(failed, {("grp_a", ("q1",)), ("grp_b", ())})

    def test_excerpt_absent_from_the_named_turn_fails(self):
        qa = copy.deepcopy(QA)
        qa[2]["evidence_anchors_json"] = json.dumps([anchor("grp_b_s01_t001", "brings the clocks", "Di", 1)])
        t = control.run_control(CONVERSATIONS, qa)["totals"]
        self.assertEqual((t["excerpt_verbatim"], t["failed_questions"]), (4, 1))

    def test_attribution_disagreement_fails_unless_listed(self):
        qa = copy.deepcopy(QA)
        qa[2]["evidence_anchors_json"] = json.dumps([anchor("grp_b_s01_t001", "moved to Tuesdays", "Ed", 1)])
        result = control.run_control(CONVERSATIONS, qa)
        self.assertFalse(result["passed"])
        self.assertEqual(result["networks"][1]["attribution_failures"], [["grp_b", "q1", "grp_b_s01_t001"]])
        with patch.dict(control.KNOWN_DISAGREEMENTS, {("grp_b", "q1", "grp_b_s01_t001"): "test"}):
            result = control.run_control(CONVERSATIONS, qa)
        self.assertTrue(result["passed"])
        self.assertEqual(result["known_disagreements_seen"],
                         [{"network": "grp_b", "qa_id": "q1", "turn_id": "grp_b_s01_t001", "agrees": False}])

    def test_canary_requires_exactly_the_evidence_turns(self):
        suites, probes = control.prepare_control(CONVERSATIONS, QA)
        probes[0].witnesses.append(("grp_a_s01", 3))  # an extra, unrelated turn
        extra = control.score_network(suites[0], probes[:2])
        self.assertEqual((extra["canary_passed"], extra["first_failed_ids"]), (1, ["q1"]))
        suites, probes = control.prepare_control(CONVERSATIONS, QA)
        probes[0].witnesses.pop()  # a missing evidence turn
        self.assertEqual(control.score_network(suites[0], probes[:2])["canary_passed"], 1)
        with self.assertRaisesRegex(ValueError, "question IDs"):
            control.score_network(suites[0], probes[:1])

    def test_planted_rows_are_restored_after_an_error(self):
        with MemoryStore(":memory:") as store:
            witnesses = [(store.add_memory(text, "episode").id, text) for text in ("one a", "two b")]
            with self.assertRaisesRegex(RuntimeError, "interrupted"):
                with control.planted_fixture(store, witnesses, "uniquetoken"):
                    hits = store.search("uniquetoken", record_access=False)
                    self.assertEqual({h.memory.id for h in hits}, {mid for mid, _ in witnesses})
                    raise RuntimeError("interrupted")
            self.assertEqual(store.search("uniquetoken", record_access=False), [])
            self.assertEqual([store.get_memory(mid).content for mid, _ in witnesses], ["one a", "two b"])

    def test_unknown_fault_and_existing_prefix_are_rejected(self):
        with self.assertRaises(ValueError):
            control.prepare_control(CONVERSATIONS, QA, fault="shuffle")
        tainted = [dict(CONVERSATIONS[0], message="text " + control.PREFIX)] + CONVERSATIONS[1:]
        with self.assertRaisesRegex(ValueError, "prefix"):
            control.prepare_control(tainted, QA)

    def test_main_writes_both_reports_and_detects_the_fault(self):
        tables = {"conversations": CONVERSATIONS, "qa": QA}
        with tempfile.TemporaryDirectory() as tmp, \
                patch.object(control, "read_release", return_value=tables):
            output = Path(tmp) / "report.json"
            code = control.main(["--data", tmp, "--output", str(output)])
            report = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual((code, report["passed"], report["rule_date"]), (0, True, "2026-11-27"))
            self.assertIn("**Passed**", output.with_suffix(".md").read_text(encoding="utf-8"))
            code = control.main(["--data", tmp, "--fault", "off-by-one", "--output", str(output)])
            report = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual((code, report["passed"], report["fault_detected"]), (0, False, True))
            self.assertIn("**Fault detected**", output.with_suffix(".md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
