# Independent LongMemEval evidence review

The category approved v3 snapshot includes 70 questions, of which 64 entered
the evaluation. Approval covers nine category decisions. Evidence groups and
update relations are still provisional. This packet includes all 70 questions
so reviewers can independently assess which cases have enough evidence.

## Generate and distribute

From a checkout with the same LongMemEval input as the recorded v3 run:

```sh
python -I experiments/longmemeval_evidence_review_packet.py \
    --data data/longmemeval/longmemeval_s_cleaned.json \
    --output /tmp/scopespool-evidence-review
```

The default annotation file is the category approved snapshot. Use
`--annotations` to select another v3 snapshot. Choose a new output directory
for each generation so a submitted ballot stays intact. Identical inputs
and `--seed` produce the same case IDs and order.

Give each reviewer a separate copy of `reviewer/`. That directory has
instructions, three batches of chronological source sessions, and a blank
JSON ballot. It presents complete turns with session dates, roles, and IDs.
It omits benchmark evidence markers, reference answers, category labels, and
proposed relations. If a reviewer asks for more context, use the case ID to
locate the question in the source dataset and supply the additional session
with its date, role, and original turn IDs.

Keep `coordinator/manifest.json` with the study coordinator until independent
ballots are submitted. The manifest maps the blinded case IDs to the source
question IDs, benchmark answers, and priority batches. It records the seed,
input hashes, and available user turn IDs. For the category approved snapshot,
batch 1 contains the seven cases whose proposed required evidence overlaps a
superseded turn. Batch 2 contains the other flagged cases. Batch 3 contains the
remaining cases. The generator verifies that all existing evidence and edge
references point to source user turns included in the packet.

## Adjudicate and freeze

1. Have reviewers work independently. Collect their answers and evidence
   groups separately from their update relations. Reviewers can mark either
   decision uncertain and explain why.
2. Check each cited turn against the source, including any additional sessions
   supplied. Check whether each required evidence group adds a fact the answer
   needs, whether the selected alternatives are genuinely equivalent, and
   whether a proposed replacement concerns the same fact, scope, and time.
3. Compare ballots and resolve disagreements against the source text. Record
   the adjudicated evidence groups, update relations, and reasons for material
   changes. Retain uncertainty where context or ordering cannot be established.
   Keep the submitted ballots and original annotation file for comparison.
4. Before detector tuning, group examples that share source turns, a fact
   family, or a scenario. Keep original examples and their edits or paraphrases
   in the same split. Assign whole groups to development and held-out sets.
   Freeze the adjudicated annotations, group assignments, cohort exclusions,
   and input hashes together.

Keep generated transcripts and reviewer ballots with the local study files.
The repository tracks the generator and procedure.
