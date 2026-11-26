# EverMemBench-Dynamic retrieval

ScopeSpool loads the five published projects independently. Each message keeps its
speaker, group, timestamp, date and original message index. Its key within the
project is `date|group|index`. Within each day and group, `related_to` links
join consecutive messages in index order. Each question keeps its original
wording and identifies how many groups contributed evidence. [Dataset and evidence schema](https://huggingface.co/datasets/EverMind-AI/EverMemBench-Dynamic) · [Hu et al., EverMemBench v3](https://arxiv.org/html/2602.01313v3)

One `R` entry names a date, group and one or more message indices or inclusive
ranges. Retrieving any referenced message covers that entry. All-required@10
counts questions for which the first ten returned messages cover every entry.
The authors supply contextual passages, so this metric measures retrieval of
cited evidence. Answer correctness requires a separate evaluation.

## Use the release

Keep the data outside the repository. With the pinned dataset checkout at
`/path/to/EverMemBench-Dynamic`, the loader reads `01/dialogue.json` and
`01/qa_01.json` through their `05/` counterparts. It verifies all input bytes
against SHA-256 digests and raises an error for an unresolved reference.
The data card lists Apache-2.0. [Pinned release](https://huggingface.co/datasets/EverMind-AI/EverMemBench-Dynamic/tree/a6b210a32248e841967b7b64a64281d2ff3f669d)

To download those ten files with the Hugging Face CLI, use the revision and
file filter below. [Download command](https://huggingface.co/docs/huggingface_hub/guides/cli#download-a-dataset-a-space-or-a-kernel)

```bash
hf download EverMind-AI/EverMemBench-Dynamic --repo-type dataset \
  --revision a6b210a32248e841967b7b64a64281d2ff3f669d \
  --include '0[1-5]/*.json' --local-dir /path/to/EverMemBench-Dynamic
```

```python
from pathlib import Path
from dynmemory.evermembench import load_topic

project = load_topic(Path("/path/to/EverMemBench-Dynamic"), "01")
question = project["queries"][0]
evidence_groups = question["required_groups"]
```

## Verify the loader

Run from the repository root. The experiment writes aggregate counts, input
digests and code digests. It keeps the source files intact.

```bash
results_dir="$(mktemp -d)"
python3 -I experiments/evermembench_control.py \
  --data /path/to/EverMemBench-Dynamic \
  --workers 2 --output "$results_dir/evermembench_control.json"
python3 -I experiments/evermembench_control.py \
  --data /path/to/EverMemBench-Dynamic --topic 01 --fault off-by-one \
  --output "$results_dir/evermembench_control_fault.json"
```

For each question with at most ten evidence entries, an independent reader
selects the highest matching message index in each raw `R` entry and appends
one unique token to each selected message. The runner restores those rows after
the search, so each question sees the original topic with just its own
witnesses marked. It loads every message of a project into an in-memory
ScopeSpool store and calls the public lexical search with a limit of ten,
without links or an embedder, and checks the converted groups against the raw
intervals. An unplanted token must return zero results. The report counts
questions above the cutoff separately.

**Run 1 failed, and the rule was changed.** The criterion first fixed was
lexical all-required@10 of 1.0 when the token is appended to the original
question. Run 1 reached 117 of 2,212 eligible questions (0.053); Codex and an
independent audit produced byte-identical reports
([run 1](../experiments/results/evermembench_control_run1_superseded/evermembench_control.json)).
The loader was not at fault: in every topic the token alone returned exactly
the planted messages and covered every entry. The rule was unachievable with
BM25, because one rare token cannot outrank messages that match several of the
question's mid-frequency words, and length normalisation penalises the long
planted messages. A test reproduces this on a small fixture.

On 2026-11-26, before run 2, the rule became: **the token-only query's lexical
top 10 covers every entry of every eligible question, and an unplanted token
returns zero results**. This checks that each planted witness is stored,
retrievable through the public search and maps back to a coordinate inside its
entry. It no longer measures whether the question text ranks the evidence; run
1's 0.053 is that measure. `--rule original` reproduces run 1. The docstring of
`experiments/evermembench_control.py` keeps the original rule and records the
change.

[Run 2](../experiments/results/evermembench_control.md) passed: 2,212 of 2,212
eligible questions across the five projects (444, 433, 439, 434 and 462), with
no hits for the unplanted token; 188 questions with more than ten entries were
counted separately. The [fault check](../experiments/results/evermembench_control_fault.md)
plants each witness one message index higher (a 0-/1-based mix-up), which is
never inside its entry; on project 01 it failed every question (0 of 444), so
the rule can fail. Both runs used the store before the lean-scan change (its
SHA-256 is in the reports).
