# Project memory notes

Updated 2026-11-24 from the Stage B shared-workspace run, spot check, label review, and retraction canaries.

## Stage B and links

- The clean Stage B run supports zero leakage, exactness, and no over-blocking across 18,177 reads; the utility reading is no cost.
- The injected `links-ignore` fault fails: 1,450 reads leaked through links and exactness was preserved for only 175 of 408 reads. Links are therefore part of the access-control and correctness boundary, not optional display metadata.
- Rebuild should carry links over, preserving source IDs and audience/workspace scope. Rebuild drops links whose other end has no live counterpart (retracted without a rebuild, or pruned). It does not check reader scope: reads filter links by audience as for any link.

## Spot check

- The reviewed output contains 20 control rows and 40 built rows. Controls: 18 `owner`, 1 `other` (R21), and 1 `unsure` (R23). Built: 34 `other`, 5 `unsure` (R11, R27, R30, R34, R59), and 1 `owner` (R55).
- Six built rows needing trace were checked against their workspace plans; none was a leak. The reviewed outcome is therefore 0 of 40 sampled hits leaking, subject to the documented sample and synthetic access-structure limits.
- The key contains arm/workspace/owner metadata, not a gold `label` column. Report arm-consistency counts rather than calling the key a direct label-accuracy oracle: strict mode is 52/60 (86.7%); the six trace-reviewed rows are annotation/uncertainty cases, not confirmed leaks.

## Label review

- `label_review/sheet_labeled.csv` adds the key-backed `repeat` field to all 75 rows: 5 repeated questions and 70 non-repeated questions.
- The original `label_review/sheet.csv` remains unchanged. Category/problem/notes remain blank because `key.json` specifies repeat status and question IDs, not category adjudications.

## Retraction

- Synthetic canaries: 500/500 trials held determinism, specificity, erasure, exact-source rebuild, and keyed-backup checks.
- Real LongMemEval text: 200/200 trials held determinism, specificity, erasure, read isolation, exact-source rebuild, and keyed-backup checks. Undeclared copied text remains a known limitation (398/398 such copies stayed readable).
- Treat links/source lists as required rebuild lineage. They are the mechanism that lets retraction identify stale derived memories; text copied without declared provenance cannot be safely rebuilt or erased.

## Implementation follow-up

- `MemoryStore.rebuild_stale` now carries links from a stale derived memory to its rebuilt replacement. The other end must be live, or stale with a live rebuild (the link then points at the rebuild). Supersession edges remain separate; links to pruned endpoints, or to endpoints retracted without a rebuild, are not resurrected.
- Added regression tests for live-link carryover, both-ends rebuild in either order, no carry to a pruned or non-rebuilt neighbour, and atomicity. The full suite (435 tests) passes.
- Run 2 (first carry-over): all 7 rules held; linked reads identical 896, same-ranking 4, different 0. Review found a gap where two linked memories both lose a source (the link was lost because the link was copied only if the other end was live at that moment); the 4 residual queries disappeared after the fix, which is consistent with that cause but was not traced query by query. Fixed: a stale end now stands for the memory that rebuilt it, and links are carried in the same transaction as the rebuild.
- Run 3 (2026-11-24, current store): all 7 rules held in 200/200 trials; linked reads identical in 900 of 900 queries; four injected faults detected. Run 1's reports are in `experiments/results/longmemeval_retraction_run1_superseded/`.
