# Adjudicate LongMemEval evidence ballots

Give each reviewer a separate copy of the blinded packet and ask for a
distinct reviewer identifier. Collect the ballots before comparing decisions
or sharing the coordinator manifest. Start with the seven older evidence
cases, continue with the other 19 flagged cases, and then review the remaining
44. The [packet guide](longmemeval_evidence_review_packet.md) explains how to
prepare a fresh packet and supply additional source context.

## Compare the first batch

Save the completed ballots and the packet's coordinator manifest in a local
study directory. From the repository root, run:

```sh
review_dir=/path/to/local/evidence_review
python -I experiments/longmemeval_adjudicate_ballots.py \
  --manifest "$review_dir/coordinator/manifest.json" \
  --ballot-a "$review_dir/reviewer_a.json" \
  --ballot-b "$review_dir/reviewer_b.json" \
  --batch older_required_overlap \
  --output "$review_dir/priority_adjudication.json"
```

Use `--batch other_flagged` or `--batch remaining` for the subsequent batches.
Omit `--batch` to require a complete ballot for every case. Save each run to a
new output file. The command refuses incomplete or invalid cases in the
selected scope and refuses to overwrite an existing worksheet.

For `supported`, supply an answer and one or more required evidence groups.
Each group is a list of alternative user turns that can satisfy the same
evidence requirement. For `unsupported` or `uncertain`, leave evidence groups
empty and explain the judgment in `notes`. Each `labelled` relation needs two
different listed user turns, a relation type, and a rationale. Leave relations
empty for `no_relation` or `uncertain`. Use `notes` to explain an uncertain
relation and give any tentative endpoints. If reviewers need extra source
context, give both reviewers the same turns, preserve the original manifest,
and record the additional verified user turn IDs in a versioned copy.

## Decide and freeze

1. Inspect the worksheet's comparison counts and attention flags. Answer
   comparison uses exact text after collapsing whitespace. Group comparison
   ignores order and counts only cases both reviewers marked supported.
   Relation comparison uses directed, typed edges and ignores rationale
   wording. Cases with an uncertain relation are omitted from the edge
   comparison. Comparison counts report how many cases each measure could
   score. The command validates turn membership and relation structure.
   Check chronology and meaning against the source.
2. Record the coordinator's decision in each blank `manual_adjudication`
   object. Set disposition to `include`, `exclude`, or `unresolved`. Confirm
   the answer, evidence groups and update relations separately, and explain
   changes or exclusions. A structural match can still contain a mistaken
   judgment. The worksheet contains the source question IDs for inspection.
   Review the two ballots and verify every chosen turn in context.
3. Record the coordinator and date, keep the original ballots and manifest,
   and create a new adjudicated annotation snapshot. Keep unresolved cases
   explicitly marked and outside any scored cohort that requires a definite
   annotation. Save the included and excluded case lists with the snapshot.
4. Assign whole groups to development and held-out sets before tuning. Group
   examples that share a source turn, fact, or scenario, including paraphrases
   and edited variants. Record group IDs and split assignment along with the
   dataset, annotation, manifest and ballot hashes. Freeze the decision rules
   with the final split before comparing models.

The worksheet includes reviewer identifiers and answers. Keep it, the
original ballots, and the benchmark transcripts in the local study files.
