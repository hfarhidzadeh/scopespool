"""Load the five EverMemBench-Dynamic projects as separate retrieval evaluation sets."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from .evaluation import load_eval_set


DATASET = "EverMind-AI/EverMemBench-Dynamic"
REVISION = "a6b210a32248e841967b7b64a64281d2ff3f669d"
# Published 01–05 directories only. Each pair pins dialogue.json and qa_<topic>.json.
FILE_HASHES = {
    "01": ("16e4fc66c47eb742cc75097ab5ea6d95e1fae8963841391e58a8e4ec35ace2dc",
           "358e22d138e24c5e655fc2c09e7f63e22e25603a065d65c946ab30ed57884d3c"),
    "02": ("37008035d1f7804a12079e4475f612a2b194b3c1c321c7a674e50d8ee57f4e0f",
           "46ac2dbe2e88b0752f9777feae4c430b033137dd84f1fe1bd749338dc4b1b446"),
    "03": ("eeb18a989e6b4f59ae23d91fcc69d8ddbee8c917793c81ae623ecee9388dc8b5",
           "81b35a8349bdbfb0f5232dfb00a48779170f3eaa2b499ad5b09de5704c19d9e7"),
    "04": ("3870ce44dfef56cebdc0236c19825eb0c5ea84e028b466e9f9fdb59349cbd56c",
           "47579156659cdedab6419d5ffa2f3030ca2a917bd3c3f134eaf16db318769797"),
    "05": ("0434cd414d01ed4fb22e37c016ee647c3d0ea5e94fe1edf7d72dcf4ae42158e8",
           "2e5038135dcc6f8ae98b3bcbf956f0d03f9086335436c84504552a2124910d2b"),
}
INDEX_RANGE = re.compile(r"([1-9][0-9]*)(?:\s*-\s*([1-9][0-9]*))?")


def read_topic_files(root: Path, topic: str) -> tuple[list, list]:
    """Read only the two source files from the pinned release for this topic."""
    if topic not in FILE_HASHES:
        raise ValueError(f"unknown EverMemBench topic {topic!r}")
    rows = []
    for name, expected in zip(("dialogue.json", f"qa_{topic}.json"), FILE_HASHES[topic]):
        path = Path(root) / topic / name
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != expected:
            raise ValueError(f"{path}: SHA-256 differs from pinned revision {REVISION}")
        rows.append(json.loads(raw))
    return rows[0], rows[1]


def _text(record: dict, field: str) -> str:
    value = record.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"missing or empty {field}")
    return value


def _reference_group(reference: dict, positions: dict) -> list[str]:
    date, channel = _text(reference, "date"), _text(reference, "group")
    index = positions.get((date, channel), {})
    keys = {}
    for part in str(reference.get("message_index", "")).split(","):
        match = INDEX_RANGE.fullmatch(part.strip())
        if not match:
            raise ValueError(f"invalid evidence index {part!r} at {date}/{channel}")
        first, last = int(match[1]), int(match[2] or match[1])
        if first > last or last - first + 1 > len(index):
            raise ValueError(f"unresolvable evidence range {part!r} at {date}/{channel}")
        for number in range(first, last + 1):
            if number not in index:
                raise ValueError(f"missing evidence message {date}/{channel}/{number}")
            keys[index[number]] = None
    return list(keys)


def topic_memories(days: list, questions: list) -> dict:
    """Convert one project's original questions, messages and inclusive evidence ranges.

    Each R entry becomes one required group of alternative messages. A hit in each
    group measures coverage of the cited passages, independently of answer quality.
    """
    if not days or not questions:
        raise ValueError("each topic needs dialogue days and questions")
    topic = _text(days[0], "topic_id")
    memories, positions, links = {}, {}, []
    for day in sorted(days, key=lambda d: _text(d, "date")):
        if _text(day, "topic_id") != topic:
            raise ValueError("mixed dialogue topics")
        date = _text(day, "date")
        for channel, messages in day["dialogues"].items():
            if not channel or "|" in channel or "|" in date:
                raise ValueError("a day and a group must be present and cannot contain '|'")
            if (date, channel) in positions:
                raise ValueError(f"duplicate day and group {date}/{channel}")
            index = positions[date, channel] = {}
            for message in messages or []:
                number = message.get("message_index")
                if type(number) is not int or number < 1 or number in index:
                    raise ValueError(f"invalid or duplicate message index {date}/{channel}/{number}")
                key = f"{date}|{channel}|{number}"
                index[number] = key
                memories[key] = {
                    "content": _text(message, "dialogue"), "kind": "episode",
                    "speaker": _text(message, "speaker"), "channel": channel,
                    "time": _text(message, "time"), "date": date, "message_index": number,
                }
            ordered = [index[number] for number in sorted(index)]
            links.extend({"source": a, "target": b, "relation": "related_to"}
                         for a, b in zip(ordered, ordered[1:]))

    queries, ids = [], set()
    for item in questions:
        qid = _text(item, "id")
        if _text(item, "topic_id") != topic or qid in ids:
            raise ValueError(f"{qid}: mixed question topics or duplicate ID")
        ids.add(qid)
        refs = item.get("R")
        if not isinstance(refs, list) or not refs:
            raise ValueError(f"{qid}: expected at least one evidence entry")
        try:
            groups = [_reference_group(ref, positions) for ref in refs]
        except ValueError as exc:
            raise ValueError(f"{qid}: {exc}") from exc
        channel_count = len({ref["group"] for ref in refs})
        queries.append({
            "id": qid, "query": _text(item, "Q"), "required_groups": groups,
            "relevant": list(dict.fromkeys(key for group in groups for key in group)),
            "tags": [f"evidence_channels_{channel_count}",
                     "cross_group" if channel_count > 1 else "single_group"],
        })
    return load_eval_set({
        "id": topic, "source": {"benchmark": DATASET, "topic": topic},
        "memories": memories, "links": links, "queries": queries,
    })


def load_topic(root: Path, topic: str) -> dict:
    """Load a single SHA-256-verified topic from an official dataset checkout."""
    suite = topic_memories(*read_topic_files(root, topic))
    if suite["id"] != topic:
        raise ValueError(f"expected topic {topic}, found {suite['id']}")
    suite["source"]["revision"] = REVISION
    return suite
