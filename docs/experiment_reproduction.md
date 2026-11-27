# Reproducing the current experiments

Run the commands from the repository root. The core test suite needs the base
package and Python 3.9 or later. CI installs the package and checks the test
suite and CLI on Python 3.9 and 3.14.

```bash
python -m pip install .
python -m unittest discover -s tests
scopespool --help
```

## Access isolation

The synthetic access experiment needs only the base package. Its current
report covers the silent default for named viewers, using schema version 7.
Write a fresh result to a scratch directory during reproduction.

```bash
results_dir="$(mktemp -d)"
python -I experiments/audience_access_channel.py --trials 500 \
  --output "$results_dir/audience_access_channel"
```

Compare the reported schema version as well as all five checks against the
[recorded after run](../experiments/results/audience_access_channel.md).

The private retention regression tests include 500 paired trials that compare
shared pruning and observer outputs while checking that the tracking reader
gains a personal entry.

```bash
python -m unittest discover -s tests -p test_per_viewer_retention.py
```

See the [private retention contract](per_viewer_retention.md) for the tested
surface and the additional work before changing the default.

Run the recorded private retention comparison and local performance benchmark
to a new output stem:

```bash
results_dir="$(mktemp -d)"
python -I experiments/private_retention_verification.py --trials 500 \
  --output "$results_dir/private_retention_verification"
```

Compare the paired outcomes with the [post-split 500-trial run](../experiments/results/private_retention_verification_post_split.md). The [original report](../experiments/results/private_retention_verification.md) covers the store before the transaction splits.
Compare performance only under a matching workload and comparable runtime.

Run the scale benchmark and its acceptance gate (about five minutes; the
recorded run used Python 3.9.6 and SQLite 3.39.5). `--smoke` runs a single
256-memory pair to check the runner. `--size`, `--repetitions`, `--embedder ngram`
(hybrid ranking; embedding writes all happen before the timed phases) and
`--src DIR` (run against another source tree, such as an exported older commit)
change the run without changing the default workload. Against the store before
the transaction split (commit 5500011), one 4,096-memory pair failed gate
criterion (a) with 5 lock errors in 72 private concurrent searches.

```bash
results_dir="$(mktemp -d)"
python -I experiments/private_retention_scale.py \
  --output "$results_dir/private_retention_scale"
python -m unittest tests.test_private_retention_races tests.test_private_retention_scale
```

The gate verdict is at the top of the report. Compare it with the
[recorded scale report](../experiments/results/private_retention_scale.md)
or, for the current store, the
[lexical](../experiments/results/private_retention_scale_speedups_py39.md) and
[n-gram](../experiments/results/private_retention_scale_speedups_ngram_py39.md)
runs on Python 3.9 (add `--embedder ngram` for the second). The exit code is
non-zero if the gate or a behavior check fails. Timings depend on the machine;
keep it awake (for example with `caffeinate -dims` on macOS) and idle.

For the authenticated server path, run the following command on a system
that supports local Unix sockets. It starts the CLI server in a separate
process and removes its temporary databases and signing key on exit.

```bash
results_dir="$(mktemp -d)"
python -I experiments/private_retention_socket.py \
  --output "$results_dir/private_retention_socket"
python -I experiments/private_retention_socket.py --fault wrong-member \
  --size 256 --repetitions 2 --output "$results_dir/private_retention_socket_fault"
python -m unittest tests.test_private_retention_socket
```

The gate (fixed in the script's docstring on 2026-11-26) is at the top of the
[socket report](../experiments/results/private_retention_socket.md). It uses
the scale benchmark's three sizes, and the wrong-member fault must fail its
attribution criteria. The recorded runs used Python 3.9.6. Use `--smoke` for
one 256-memory pair.

The EverMemBench canary control and audience test need the pinned data files; see
[EverMemBench](evermembench.md) for the download, hashes and commands.

## LongMemEval v3 and detector baselines

Place the cleaned LongMemEval S file at
`data/longmemeval/longmemeval_s_cleaned.json` using the data instructions in the
[README](../README.md#longmemeval-knowledge-updates). The recorded runs use the
category-approved snapshot and the all-MiniLM-L6-v2 model through
sentence-transformers 3.4.1 and torch 2.2.2. Install the embedding extra in a
virtual environment with the model available in its Hugging Face cache. Set
the offline flags once the model is available.

```bash
annotation_file=eval/longmemeval_knowledge_update_annotations_v3_category_approved_2026-11-25.json
results_dir="$(mktemp -d)"
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 python -I experiments/longmemeval_v3.py \
  --annotations "$annotation_file" --output "$results_dir/longmemeval_v3"
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 python -I experiments/longmemeval_detector_baselines.py \
  --annotations "$annotation_file" --output "$results_dir/longmemeval_detector_baselines"
```

Both scripts produce Markdown and JSON. Compare the full dataset and annotation
hashes, the 64-question cohort, and the control results with the recorded
[v3 run](../experiments/results/longmemeval_v3_category_approved_2026-11-25.md)
and [detector run](../experiments/results/longmemeval_detector_baselines_category_approved_2026-11-25.md).
Each script also accepts `--semantic ngram` for a local smoke run using a
different backend. Record the backend and dependency versions with any results.
The owner's approval covers nine categories. Evidence groups and update
relations are still provisional.

## History retrieval pilot and evidence review

Use the same data and category-approved snapshot for the
[history retrieval pilot](../experiments/results/longmemeval_history_retrieval_pilot.md).
The lexical pilot needs the base package only. This command supplies query
intent from the annotations so the run measures the ranking policy.

```bash
results_dir="$(mktemp -d)"
python -I experiments/longmemeval_history_retrieval.py \
  --oracle-intent-from-annotations --output "$results_dir/history_retrieval"
python -I experiments/longmemeval_evidence_review_packet.py \
  --output "$results_dir/evidence_review"
```

The [evidence review guide](longmemeval_evidence_review_packet.md) explains
how to distribute the blinded packets and adjudicate the ballots.
Use the [adjudication command](longmemeval_adjudication.md) after both ballots
are returned. The [paraphrase dispute packet](longmemeval_paraphrase_review.md)
has a separate generator and reviewer rubric.
