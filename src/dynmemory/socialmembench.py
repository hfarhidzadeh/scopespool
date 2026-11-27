"""Load SocialMemBench networks as separate retrieval evaluation sets.

The release ships four flat Parquet files. Nested values (evidence anchors,
active participants, options) are JSON strings inside string columns, so a
small reader for flat, single-level Parquet with Snappy or no compression is
enough; it rejects anything else rather than guess. Each network becomes one
evaluation set keyed by the dataset's own ``turn_id``. Each question keeps its
original wording and its evidence anchors (turn ID, verbatim excerpt, speaker
and session as the anchor states them); the answer is never copied.
"""

from __future__ import annotations

import hashlib
import json
import struct
from pathlib import Path

from .evaluation import load_eval_set


DATASET = "qunlexie/SocialMemBench"
REVISION = "efd0a5f526871437943d385a59ea93339ef61438"
LICENSE = "CC-BY-4.0"
# SHA-256 of each top-level file at REVISION (equal to the Hugging Face LFS object IDs).
FILE_HASHES = {
    "conversations.parquet": "f9ed5d10501cd8a46ca09bb914866ae3069136c259d99ee24dd175e30c90c88d",
    "qa.parquet": "98990f88a25df0d9a017488d39ca50e76f432b6554c67b2beafa5f9421ee3f5e",
    "networks.parquet": "e85e7bfd5fd61bf4d5cbd7ad49b3c57a945198480e6c2dba46499fba1ced1a57",
    "personas.parquet": "723d941291a0c5ce30c9892670cd7571796d6e0b0b6487212009c3a1ed026a62",
}
TURN_FIELDS = ("network_id", "session_id", "session_index", "turn_id", "speaker_persona_id",
               "speaker_display_name", "timestamp", "message", "message_index")


# --- Minimal Parquet reader (flat schemas only) ------------------------------------

_PHYSICAL = {0: "BOOLEAN", 1: "INT32", 2: "INT64", 4: "FLOAT", 5: "DOUBLE", 6: "BYTE_ARRAY"}
_PLAIN, _PLAIN_DICTIONARY, _RLE, _RLE_DICTIONARY = 0, 2, 3, 8
_UNCOMPRESSED, _SNAPPY = 0, 1


class _Thrift:
    """Decode Thrift compact-protocol structs into {field id: value} dicts."""

    def __init__(self, data: bytes, pos: int = 0):
        self.data, self.pos = data, pos

    def byte(self) -> int:
        value = self.data[self.pos]
        self.pos += 1
        return value

    def varint(self) -> int:
        shift = result = 0
        while True:
            b = self.byte()
            result |= (b & 0x7F) << shift
            if not b & 0x80:
                return result
            shift += 7
            if shift > 70:
                raise ValueError("Parquet metadata: varint too long")

    def zigzag(self) -> int:
        n = self.varint()
        return (n >> 1) ^ -(n & 1)

    def value(self, kind: int):
        if kind in (1, 2):
            return kind == 1
        if kind == 3:
            return struct.unpack("b", bytes([self.byte()]))[0]
        if kind in (4, 5, 6):
            return self.zigzag()
        if kind == 7:
            self.pos += 8
            return struct.unpack_from("<d", self.data, self.pos - 8)[0]
        if kind == 8:
            size = self.varint()
            self.pos += size
            if self.pos > len(self.data):
                raise ValueError("Parquet metadata: truncated binary field")
            return bytes(self.data[self.pos - size:self.pos])
        if kind in (9, 10):
            header = self.byte()
            size, element = header >> 4, header & 0x0F
            if size == 15:
                size = self.varint()
            if element in (1, 2):
                return [self.byte() == 1 for _ in range(size)]
            return [self.value(element) for _ in range(size)]
        if kind == 11:
            size = self.varint()
            if not size:
                return {}
            types = self.byte()
            return {self.value(types >> 4): self.value(types & 0x0F) for _ in range(size)}
        if kind == 12:
            return self.struct()
        raise ValueError(f"Parquet metadata: unsupported Thrift type {kind}")

    def struct(self) -> dict:
        fields, last = {}, 0
        while True:
            header = self.byte()
            if header == 0:
                return fields
            delta, kind = header >> 4, header & 0x0F
            last = last + delta if delta else self.zigzag()
            fields[last] = self.value(kind)


def snappy_decompress(data: bytes) -> bytes:
    """Decompress one raw Snappy block (the format Parquet uses, without framing)."""
    reader = _Thrift(data)
    expected = reader.varint()
    pos, out = reader.pos, bytearray()
    while pos < len(data):
        tag = data[pos]
        pos += 1
        kind = tag & 3
        if kind == 0:
            length = tag >> 2
            if length >= 60:
                extra = length - 59
                length = int.from_bytes(data[pos:pos + extra], "little")
                pos += extra
            length += 1
            if pos + length > len(data):
                raise ValueError("Snappy: truncated literal")
            out += data[pos:pos + length]
            pos += length
            continue
        if kind == 1:
            length = ((tag >> 2) & 7) + 4
            offset = ((tag >> 5) << 8) | data[pos]
            pos += 1
        else:
            width = 2 if kind == 2 else 4
            length = (tag >> 2) + 1
            offset = int.from_bytes(data[pos:pos + width], "little")
            pos += width
        if offset <= 0 or offset > len(out):
            raise ValueError("Snappy: copy offset outside the output")
        start = len(out) - offset
        if offset >= length:
            out += out[start:start + length]
        else:
            while length > 0:
                chunk = out[start:start + min(length, offset)]
                out += chunk
                length -= len(chunk)
    if len(out) != expected:
        raise ValueError("Snappy: decompressed length differs from the header")
    return bytes(out)


def _hybrid(data: bytes, pos: int, end: int, width: int, count: int) -> list[int]:
    """Decode the RLE/bit-packed hybrid encoding until ``count`` values are read."""
    values: list[int] = []
    reader = _Thrift(data, pos)
    size = (width + 7) // 8
    mask = (1 << width) - 1
    while len(values) < count:
        if reader.pos >= end:
            raise ValueError("Parquet: RLE run ends before all values were read")
        header = reader.varint()
        if header & 1:
            groups = header >> 1
            nbytes = groups * width
            chunk = int.from_bytes(data[reader.pos:reader.pos + nbytes], "little")
            reader.pos += nbytes
            values.extend((chunk >> (i * width)) & mask for i in range(groups * 8))
        else:
            value = int.from_bytes(data[reader.pos:reader.pos + size], "little")
            reader.pos += size
            values.extend([value] * (header >> 1))
    return values[:count]


def _plain(data: bytes, pos: int, physical: str, count: int, text: bool) -> list:
    if physical == "BYTE_ARRAY":
        values = []
        for _ in range(count):
            size = int.from_bytes(data[pos:pos + 4], "little")
            pos += 4
            raw = data[pos:pos + size]
            if len(raw) != size:
                raise ValueError("Parquet: truncated byte array")
            pos += size
            values.append(raw.decode("utf-8") if text else bytes(raw))
        return values
    if physical == "BOOLEAN":
        return [bool((data[pos + i // 8] >> (i % 8)) & 1) for i in range(count)]
    code = {"INT32": "i", "INT64": "q", "FLOAT": "f", "DOUBLE": "d"}[physical]
    return list(struct.unpack_from(f"<{count}{code}", data, pos))


def read_parquet(path: Path) -> list[dict]:
    """Read every row of a flat Parquet file into dicts (column name -> value or None)."""
    data = Path(path).read_bytes()
    if len(data) < 12 or data[:4] != b"PAR1" or data[-4:] != b"PAR1":
        raise ValueError(f"{path}: not a Parquet file")
    footer = int.from_bytes(data[-8:-4], "little")
    meta = _Thrift(data, len(data) - 8 - footer).struct()
    schema = meta[2]
    if len(schema) != 1 + schema[0].get(5, 0):
        raise ValueError(f"{path}: nested Parquet schemas are not supported")
    columns = []
    for element in schema[1:]:
        if 5 in element or element.get(3, 0) == 2 or element.get(1) not in _PHYSICAL:
            raise ValueError(f"{path}: only flat required/optional primitive columns are supported")
        logical = element.get(10, {})
        text = element.get(6) == 0 or 1 in logical
        columns.append((element[4].decode("utf-8"), _PHYSICAL[element[1]], element.get(3, 0) == 1, text))
    names = [name for name, *_ in columns]
    if len(set(names)) != len(names):
        raise ValueError(f"{path}: duplicate column names")
    rows: list[dict] = []
    for group in meta.get(4, []):
        nrows = group[3]
        if len(group[1]) != len(columns):
            raise ValueError(f"{path}: row group has {len(group[1])} columns, schema has {len(columns)}")
        table = {}
        for chunk, (name, physical, optional, text) in zip(group[1], columns):
            info = chunk[3]
            if [p.decode("utf-8") for p in info[3]] != [name] or _PHYSICAL.get(info[1]) != physical:
                raise ValueError(f"{path}: column chunk does not match schema column {name}")
            table[name] = _read_chunk(data, info, physical, optional, text, path)
            if len(table[name]) != nrows:
                raise ValueError(f"{path}: column {name} has {len(table[name])} values, expected {nrows}")
        rows.extend({name: table[name][i] for name in names} for i in range(nrows))
    if len(rows) != meta[3]:
        raise ValueError(f"{path}: read {len(rows)} rows, footer says {meta[3]}")
    return rows


def _read_chunk(data: bytes, info: dict, physical: str, optional: bool, text: bool, path) -> list:
    codec = info[4]
    if codec not in (_UNCOMPRESSED, _SNAPPY):
        raise ValueError(f"{path}: unsupported compression codec {codec}")
    total = info[5]
    pos = info.get(11) or info[9]
    dictionary, values = None, []
    while len(values) < total:
        reader = _Thrift(data, pos)
        header = reader.struct()
        body_start, size = reader.pos, header[3]
        body = data[body_start:body_start + size]
        pos = body_start + size
        kind = header[1]
        if kind == 2:  # dictionary page
            raw = snappy_decompress(body) if codec == _SNAPPY else body
            page = header[7]
            if page.get(2, _PLAIN) not in (_PLAIN, _PLAIN_DICTIONARY):
                raise ValueError(f"{path}: unsupported dictionary encoding")
            dictionary = _plain(raw, 0, physical, page[1], text)
            continue
        if kind == 0:
            page = header[5]
            raw = snappy_decompress(body) if codec == _SNAPPY else body
            count, encoding, cursor = page[1], page[2], 0
            defined = [1] * count
            if optional:
                length = int.from_bytes(raw[:4], "little")
                defined = _hybrid(raw, 4, 4 + length, 1, count)
                cursor = 4 + length
        elif kind == 3:
            page = header[8]
            count, encoding = page[1], page[4]
            def_len, rep_len = page[5], page[6]
            if rep_len:
                raise ValueError(f"{path}: repetition levels in a flat column")
            levels, rest = body[:def_len], body[def_len:]
            compressed = page.get(7, True) and codec == _SNAPPY
            raw = snappy_decompress(rest) if compressed else rest
            defined = _hybrid(levels, 0, def_len, 1, count) if optional else [1] * count
            cursor = 0
        else:
            raise ValueError(f"{path}: unsupported page type {kind}")
        present = sum(defined)
        if encoding == _PLAIN:
            decoded = _plain(raw, cursor, physical, present, text)
        elif encoding in (_PLAIN_DICTIONARY, _RLE_DICTIONARY):
            if dictionary is None:
                raise ValueError(f"{path}: dictionary-encoded page without a dictionary")
            width = raw[cursor]
            indices = _hybrid(raw, cursor + 1, len(raw), width, present) if present else []
            if any(i >= len(dictionary) for i in indices):
                raise ValueError(f"{path}: dictionary index out of range")
            decoded = [dictionary[i] for i in indices]
        elif encoding == _RLE and physical == "BOOLEAN":
            length = int.from_bytes(raw[cursor:cursor + 4], "little")
            decoded = [bool(v) for v in _hybrid(raw, cursor + 4, cursor + 4 + length, 1, present)]
        else:
            raise ValueError(f"{path}: unsupported encoding {encoding}")
        it = iter(decoded)
        values.extend(next(it) if flag else None for flag in defined)
    if len(values) != total:
        raise ValueError(f"{path}: column has more values than its metadata")
    return values


# --- Release files ------------------------------------------------------------------

def read_release(root: Path, verify: bool = True, names=("conversations.parquet", "qa.parquet")) -> dict:
    """Read release files from a local copy, checking SHA-256 against REVISION by default."""
    tables = {}
    for name in names:
        if name not in FILE_HASHES:
            raise ValueError(f"unknown SocialMemBench file {name!r}")
        path = Path(root) / name
        if verify and hashlib.sha256(path.read_bytes()).hexdigest() != FILE_HASHES[name]:
            raise ValueError(f"{path}: SHA-256 differs from pinned revision {REVISION}")
        tables[name.split(".")[0]] = read_parquet(path)
    return tables


def _text(record: dict, field: str) -> str:
    value = record.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"missing or empty {field}")
    return value


def _index(record: dict, field: str) -> int:
    value = record.get(field)
    if type(value) is not int or value < 1:
        raise ValueError(f"{field} must be a positive integer, got {value!r}")
    return value


def group_turns(rows: list[dict]) -> dict:
    """Group conversation rows by network, ordered by session and message index."""
    networks: dict = {}
    seen, coordinates, sessions = set(), set(), {}
    for row in rows:
        try:
            turn = {field: _text(row, field) for field in TURN_FIELDS
                    if field not in ("session_index", "message_index")}
            turn["session_index"] = _index(row, "session_index")
            turn["message_index"] = _index(row, "message_index")
        except ValueError as exc:
            raise ValueError(f"turn {row.get('turn_id')!r}: {exc}") from exc
        turn["session_date"] = row.get("session_date") or None
        turn["reply_to"] = row.get("reply_to_turn_id") or None
        tid, net = turn["turn_id"], turn["network_id"]
        if tid in seen:
            raise ValueError(f"duplicate turn_id {tid!r}")
        seen.add(tid)
        coordinate = (net, turn["session_index"], turn["message_index"])
        if coordinate in coordinates:
            raise ValueError(f"duplicate message index {coordinate}")
        coordinates.add(coordinate)
        if sessions.setdefault((net, turn["session_index"]), turn["session_id"]) != turn["session_id"]:
            raise ValueError(f"session {coordinate[:2]} has more than one session_id")
        networks.setdefault(net, []).append(turn)
    for turns in networks.values():
        turns.sort(key=lambda t: (t["session_index"], t["message_index"]))
    return networks


def parse_anchors(item: dict) -> list[dict]:
    """Parse one question's evidence anchors from the JSON string the release stores."""
    raw = item.get("evidence_anchors_json")
    anchors = json.loads(raw) if isinstance(raw, str) else raw
    if not isinstance(anchors, list) or not anchors:
        raise ValueError("expected at least one evidence anchor")
    parsed = []
    for anchor in anchors:
        if not isinstance(anchor, dict):
            raise ValueError("an evidence anchor must be an object")
        parsed.append({"turn_id": _text(anchor, "turn_id"),
                       "excerpt": _text(anchor, "message_excerpt"),
                       "speaker": anchor.get("speaker_display_name"),
                       "session_index": anchor.get("session_index")})
    return parsed


def network_memories(network_id: str, turns: list[dict], questions: list[dict]) -> dict:
    """Convert one network's turns and questions into a ScopeSpool evaluation set.

    Keys are the release's turn IDs, used as opaque strings: their numeric
    suffix does not consistently equal ``message_index`` (or ``message_index - 1``).
    Each distinct anchored turn is one required group.
    """
    if not turns or not questions:
        raise ValueError(f"{network_id}: each network needs turns and questions")
    memories, links, previous = {}, [], None
    for turn in turns:
        if turn["network_id"] != network_id:
            raise ValueError(f"{network_id}: turn {turn['turn_id']} belongs to another network")
        memories[turn["turn_id"]] = {
            "content": turn["message"], "kind": "episode",
            "speaker": turn["speaker_display_name"], "speaker_id": turn["speaker_persona_id"],
            "channel": network_id, "session_id": turn["session_id"],
            "session_index": turn["session_index"], "message_index": turn["message_index"],
            "time": turn["timestamp"], "date": turn["session_date"], "reply_to": turn["reply_to"],
        }
        if previous and previous["session_id"] == turn["session_id"]:
            links.append({"source": previous["turn_id"], "target": turn["turn_id"],
                          "relation": "related_to"})
        previous = turn

    queries, ids = [], set()
    for item in questions:
        qid = _text(item, "qa_id")
        if item.get("network_id") != network_id or qid in ids:
            raise ValueError(f"{qid}: question from another network or duplicate ID")
        ids.add(qid)
        try:
            anchors = parse_anchors(item)
        except ValueError as exc:
            raise ValueError(f"{qid}: {exc}") from exc
        for anchor in anchors:
            if anchor["turn_id"] not in memories:
                raise ValueError(f"{qid}: evidence turn {anchor['turn_id']!r} is not in {network_id}")
        keys = list(dict.fromkeys(anchor["turn_id"] for anchor in anchors))
        session_count = len({memories[key]["session_id"] for key in keys})
        queries.append({
            "id": qid, "query": _text(item, "question"),
            "required_groups": [[key] for key in keys], "relevant": keys,
            "evidence": [{"key": a["turn_id"], "excerpt": a["excerpt"], "speaker": a["speaker"],
                          "session_index": a["session_index"]} for a in anchors],
            "tags": [str(item.get("query_type")), str(item.get("difficulty")),
                     str(item.get("answer_format")), f"evidence_turns_{len(keys)}",
                     "cross_session" if session_count > 1 else "single_session"],
        })
    return load_eval_set({
        "id": network_id, "source": {"benchmark": DATASET, "network": network_id},
        "memories": memories, "links": links, "queries": queries,
    })


def build_networks(conversations: list[dict], qa: list[dict]) -> list[dict]:
    """Convert release rows into one evaluation set per network, sorted by network ID."""
    networks = group_turns(conversations)
    questions: dict = {}
    for item in qa:
        questions.setdefault(item.get("network_id"), []).append(item)
    unknown = set(questions) - set(networks)
    if unknown:
        raise ValueError(f"questions for networks without turns: {sorted(map(str, unknown))}")
    return [network_memories(net, networks[net], questions.get(net, []))
            for net in sorted(networks)]


def load_networks(root: Path, verify: bool = True) -> list[dict]:
    """Load every network from a local copy of the pinned release."""
    tables = read_release(root, verify=verify)
    suites = build_networks(tables["conversations"], tables["qa"])
    for suite in suites:
        suite["source"]["revision"] = REVISION if verify else None
    return suites
