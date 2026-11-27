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

[Run 2](../experiments/results/evermembench_control_run2_superseded/evermembench_control.md)
passed: 2,212 of 2,212 eligible questions across the five projects (444, 433,
439, 434 and 462), with no hits for the unplanted token; 188 questions with
more than ten entries were counted separately. Its fault check plants each
witness one message index higher (a 0-/1-based mix-up), which is never inside
its entry; on project 01 it failed every question (0 of 444), so the rule can
fail. Run 2 used the store from before the lean-scan change.

[Run 3](../experiments/results/evermembench_control.md) repeats run 2 on the
committed store (revision 9a2b964, store SHA-256 `f88e788c…`, recorded in the
report) with the same pinned inputs. Its totals and every per-topic result are
identical to run 2: 2,212 of 2,212, no unplanted-token hits. The
[fault check](../experiments/results/evermembench_control_fault.md) again
failed every project 01 question (0 of 444).

## Retrieval experiment (draft, not run)

`experiments/evermembench_retrieval.py` holds a draft pre-registration, dated
2026-11-26 and awaiting the researcher's approval. It would compare lexical
and hybrid search, each with and without links, on all-required@10, group
coverage@10 and first-hit reciprocal rank, by the number of evidence groups a
question needs (1, 2–3, 4–10; questions with more than ten are reported
separately because they cannot reach all-required@10). Before any reading, the
canary control must pass, an oracle ranking must score 1.0, and questions
searched in another topic's store must score near zero. Comparisons use paired
bootstrap intervals and sign-flip tests with a Holm adjustment. The script
exits before reading data unless `--approved` is passed; `--smoke` writes only
outside `experiments/results/`. A full run is estimated at one to two hours.

## Audience test

`experiments/evermembench_audience.py` asks whether group boundaries hold on
real multi-group histories. Each project's groups become channels; each
speaker joins every group they posted in, and each message is written as its
speaker. For every cross-group question, a fixed seed picks an asker who posted
in some but not all of the cited groups. Three searches are compared: FULL (the
whole project store, searched as the asker), VISIBLE (a store holding only the
asker's groups, searched as the asker) and POWER (the full store, searched by a
synthetic member of every group). Its rules were fixed in the script's
docstring on 2026-11-26:

1. Determinism: project 01 processed twice gives identical results.
2. Power: POWER ranks cited evidence from a group hidden from the asker in its
   top 10 in at least 25% of questions; otherwise rules 3 and 4 could pass
   without testing anything.
3. Noninterference: FULL and VISIBLE return the same keys in the same order,
   with scores within 1e-9, so hidden groups cannot shift scores either.
4. No message from a hidden group appears in FULL's top 10.

A leak fault (FULL searched without viewers) must fail rules 3 and 4 each in at
least 25% of questions.

The [recorded run](../experiments/results/evermembench_audience.md) covered all
791 cross-group questions in projects 01–05 (none skipped, 125 distinct
askers) on the store with SHA-256 `40258276…`. Verdict: no leak across
groups. Rule 1 held; rule 2 held in 354 of 791 questions (44.8%); rules 3 and 4
held in all 791. All-required@10 over the cited groups the asker can see was
0.059. The [fault run](../experiments/results/evermembench_audience_fault.md)
failed rule 3 in 791 of 791 questions and rule 4 in 729 of 791, so the test
detects the leak it is for.

**Hybrid search.** `--embedder ngram` runs the same workload with every store
built with `NGramHashEmbedder` (character 3-grams, 512 dimensions,
`min_similarity` 0.25), so search fuses the lexical and vector rankings. Its
rules were written in the script's docstring on 2026-11-27, before any n-gram
run: the same four rules, the same 1e-9 score tolerance and the same fault
criterion. Hidden memories are dropped before both rankings, a cosine score
depends only on the memory's own vector, and the fusion and normalisation use
visible memories only, so any score difference would be a leak. A unit test
plants a fault that only takes the top cosine matches over the whole store
before dropping hidden ones; rule 3 catches it through the scores alone. The
[n-gram run](../experiments/results/evermembench_audience_ngram.md) covered the
same 791 questions on the store with SHA-256 `40258276…`. Verdict: no leak
across groups. Rule 1 held; rule 2 held in 307 of 791 questions (38.8%); rules
3 and 4 held in all 791. All-required@10 was 0.038. The
[n-gram fault run](../experiments/results/evermembench_audience_ngram_fault.md)
failed rule 3 in 791 of 791 and rule 4 in 749 of 791. The store has changed
since only in how prune reads its candidates, which search does not use. The
n-gram embedder matches spelling, not meaning, so this tests the vector path's
isolation, not a semantic model's.

Limits: the asker is staged, since the dataset names none; membership is
inferred from who posted, so members who never posted are missing; membership
is not dated, so a member reads a group's whole history; there is no roster;
group names only mean something within one project; the default run is
lexical, and the hybrid run uses only the n-gram baseline embedder.

```bash
python3 -I experiments/evermembench_audience.py --data /path/to/EverMemBench-Dynamic \
  --output "$results_dir/evermembench_audience"
python3 -I experiments/evermembench_audience.py --data /path/to/EverMemBench-Dynamic \
  --fault leak --output "$results_dir/evermembench_audience_fault"
python3 -I experiments/evermembench_audience.py --data /path/to/EverMemBench-Dynamic \
  --embedder ngram --output "$results_dir/evermembench_audience_ngram"
python3 -I experiments/evermembench_audience.py --data /path/to/EverMemBench-Dynamic \
  --embedder ngram --fault leak --output "$results_dir/evermembench_audience_ngram_fault"
```

Each lexical run took about 25 minutes on Python 3.9; the n-gram runs took 44
minutes (normal) and 61 minutes (fault) on a shared, loaded machine.
