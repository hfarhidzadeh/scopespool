# Adjudicate LongMemEval paraphrase ballots

Give each reviewer a separate copy of the [paraphrase packet](longmemeval_paraphrase_review.md).
Have them assign distinct reviewer IDs and return their completed JSON files
independently. Keep the original reviewer ZIP and the corresponding coordinator
manifest. Ballots contain case IDs but do not have a packet fingerprint, so keep
submitted ballots with the packet they reviewed.

## Compare the ballots

From the repository root, point `review_dir` to the local study folder. Replace
the two ballot filenames with the files returned by the reviewers.

```sh
review_dir=/path/to/local/paraphrase_review
python -I experiments/longmemeval_adjudicate_paraphrases.py \
  --manifest "$review_dir/coordinator/manifest.json" \
  --packet "$review_dir/longmemeval_paraphrase_reviewer_packet.zip" \
  --ballot-a "$review_dir/reviewer_a.json" \
  --ballot-b "$review_dir/reviewer_b.json" \
  --output "$review_dir/adjudication.json"
```

The command checks the original ZIP against the manifest hash. Both ballots
must cover all manifest case IDs. Every case needs a usability judgment and a
rationale. Usable cases require one of `equivalent`, `incompatible`,
`distinct_compatible`, or `open`. Unusable cases need a null relation and a
rationale for exclusion. Notes can be text or null. The worksheet records
input hashes and refuses to overwrite an existing file.

## Adjudicate and freeze the split

1. Review usability and relation agreement separately, both overall and by
   source family. Only cases both reviewers marked usable enter the relation
   comparison. A usable `open` vote counts as a relation judgment. Unusable
   votes are counted separately. The attention flags identify disagreements,
   open judgments, and unusable examples.
2. Read the judgments and source context and record a human decision in each
   blank `manual_adjudication` object. Record supporting reasons and any extra
   context. Keep unresolved, usable examples as `open` when appropriate.
3. After adjudication, copy the worksheet's `family_split` object to a new
   JSON file and assign each whole family to `development` or `holdout`. Check
   for repeated claims and related scenarios across families and assign
   related families together. Pass the file with `--family-split` and use a
   new worksheet path to verify coverage and check that no source question
   or session appears in both splits. This creates a fresh worksheet, so
   preserve the completed adjudication file as its own input to evaluation.
4. Freeze the adjudicated labels, unusable cases, family split, input hashes,
   and scoring rules before evaluation. Preserve both original ballots.

Keep ballots and adjudication worksheets in the local study folder.
