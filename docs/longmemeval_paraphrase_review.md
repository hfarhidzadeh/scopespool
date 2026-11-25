# LongMemEval paraphrase dispute review

This packet is a pilot for reviewing when differently worded claims should
count as the same claim in a dispute. It contains 48 pairs from 12 source
families, with four variants for each source excerpt. The excerpts come from
LongMemEval's single-session user questions. This keeps the selected question
IDs apart from the v3 knowledge-update evidence review. Codex drafted the fixed
variants for this study. The pairs await independent human review.

## Generate the packet

Run from the repository root with a copy of cleaned LongMemEval S:

```sh
python -I experiments/longmemeval_paraphrase_review_packet.py \
    --data data/longmemeval/longmemeval_s_cleaned.json \
    --output /tmp/scopespool-paraphrase-review
```

Use a new output directory for each run. The default seed shuffles the pairs
and the sides within each pair. Identical inputs and seed reproduce the same
case IDs, contents, and archive hash.

Give each reviewer their own copy of
`longmemeval_paraphrase_reviewer_packet.zip`. It contains the rubric, claim
pairs, and a blank ballot. The reviewer files omit source IDs, variant design
notes, and adjudicated labels. Keep the separate `coordinator/manifest.json`
with the study coordinator. It records the source family, question, session,
turn, and character offsets in the original user text, along with authored
variant provenance and input hashes. Design notes describe what a variant
changes. Reviewers decide its relation independently.

## Review

Have two reviewers fill the ballots independently, using the shown time,
speaker labels, and claim text. The four relations are `equivalent`,
`incompatible`, `distinct_compatible`, and `open`. Compare the subject, time,
scope, entity, value, and negation. For first-person statements, resolve the
subject using each claim's attributed speaker. Allow equivalent wording and
unit conversions. Leave a case open when the information shown cannot settle
the relation. Flag broken excerpts or misleading phrasing as unusable and
record the reason.

Reconcile disagreements after both ballots are submitted. Keep the original
ballots, any extra context shown, and the adjudication rationale. Keep
unresolved cases available to evaluate abstention. The synthetic speaker
labels test attribution only. The later dispute experiment should evaluate
actual resolution rules, audience visibility, and authority separately.

## Holdout

Freeze reviewed labels, exclusions, source and archive hashes, and the split
before scoring any method. Keep every variant of a source family in the same
split. Check for overlapping sessions, repeated claims, and related scenarios
before assigning families. Group such overlaps together across the
development and holdout sets. Treat the small family count as a pilot and use
more independently reviewed families for a larger study.

Compare exact matching and equivalence candidates on the same held-out pairs.
Report false merges of incompatible or distinct claims and how often ambiguous
claims remain unresolved. Then test audience visibility and speaker authority
in the dispute experiment. Keep generated excerpts and ballots with the local
research files.
