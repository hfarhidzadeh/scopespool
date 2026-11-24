# ScopeSpool project memory notes

Updated 2026-11-24 with Stage B, retraction run 3, the shared read trace decision, and the v3 annotation review.

## Stage B and links

- The [Stage B run](../experiments/results/longmemeval_shared_workspace.md) covered 601 workspaces and 18,177 reads. There were zero observed leaks, all rankings matched their visibility reference, and all 2,704 visible canaries were found. Owner RR@10 was 0.6464 with filtering before ranking and 0.6568 with filtering after ranking over all candidates. The difference of −0.0104 was within the preset 0.02 margin.
- The [`links-ignore` fault](../experiments/results/longmemeval_shared_workspace_fault_links_ignore.md) exposed 1,450 hidden link endpoints in 408 reads. Only 175 reads matched their reference. All six Stage B fault controls showed their expected pattern.
- Stage B uses real text in constructed workspaces with silent reads. Cross-user disputes on real text are a separate follow-up.
- Rebuild should carry links over, preserving source IDs and audience/workspace scope. Rebuild drops links whose other end has no live counterpart (retracted without a rebuild, or pruned). It does not check reader scope: reads filter links by audience as for any link.

## Spot check

- The reviewed output contains 20 control rows and 40 built rows. Controls: 18 `owner`, 1 `other` (R21), and 1 `unsure` (R23). Built: 34 `other`, 5 `unsure` (R11, R27, R30, R34, R59), and 1 `owner` (R55).
- Six built rows needing trace were checked against their workspace plans; none was a leak. The reviewed outcome is therefore 0 of 40 sampled hits leaking, subject to the documented sample and synthetic access-structure limits.
- The key contains arm, workspace, and speaker metadata. The historical comparison's 52/60 (86.7%) measures agreement with arm expectations. The workspace traces resolved all six built rows requiring follow-up. See the [spot-check outcome](../experiments/results/spot_check/outcome.md).

## Label review

- The 75-row evidence-based AI review passed 5/5 repeat pairs. For the 70 unique questions it agreed with 65 original labels and 68 recommendations from the prior AI review. The key-backed repeat export in `label_review/sheet_labeled.csv` is a separate bookkeeping file.
- Category decisions for the follow-up: `2133c1b5` is `exclude` because the answer follows the question. `5c40ec5b`, `cf22b7bf`, `26bdc477`, and `42ec0761` are `context`. The older turns give a first meeting without a count, a different weight-loss interval, three example trips without a total, and a misplaced regular screwdriver without establishing prior ownership of a spare, respectively.

## Retraction

- Synthetic canaries: 500/500 trials held determinism, specificity, erasure, exact-source rebuild, and keyed-backup checks.
- Real LongMemEval text: 200/200 trials held determinism, specificity, erasure, read isolation, exact-source rebuild, and keyed-backup checks. Undeclared copied text remains a known limitation (398/398 such copies stayed readable).
- Treat links/source lists as required rebuild lineage. They are the mechanism that lets retraction identify stale derived memories; text copied without declared provenance cannot be safely rebuilt or erased.

## Implementation follow-up

- `MemoryStore.rebuild_stale` now carries links from a stale derived memory to its rebuilt replacement. The other end must be live, or stale with a live rebuild (the link then points at the rebuild). Supersession edges remain separate; links to pruned endpoints, or to endpoints retracted without a rebuild, are not resurrected.
- Added regression tests for live-link carryover, both-ends rebuild in either order, no carry to a pruned or non-rebuilt neighbour, and atomicity. The full suite (435 tests) passes.
- Run 2 (first carry-over): all 7 rules held; linked reads identical 896, same-ranking 4, different 0. Review found a gap where two linked memories both lose a source (the link was lost because the link was copied only if the other end was live at that moment); the 4 residual queries disappeared after the fix, which is consistent with that cause but was not traced query by query. Fixed: a stale end now stands for the memory that rebuilt it, and links are carried in the same transaction as the rebuild.
- [Run 3](../experiments/results/longmemeval_retraction.md) (2026-11-24): all seven rules held in 200/200 trials. Both linked (900/900) and unlinked (898/898) query results matched the never-written reference, and all four injected faults were detected. The rebuilt memories use extractive joins and declared sources. Run 1's reports are in `experiments/results/longmemeval_retraction_run1_superseded/`.

## Shared read traces

- The [before run](../experiments/results/audience_access_channel.md) held rules 1–4 in 500/500 synthetic trials. The trace rule held in 0/500. A fellow channel member could infer the topic from the shared counters or from which memories survived pruning in 500/500 trials. The ranking and hidden-channel fault controls each failed their intended rule in 100/100 trials.
- Decision for implementation: when `viewers` is supplied, an omitted `record_access` means silent. Keep `record_access=True` as an explicit opt-in and keep the existing unscoped default. Apply the default consistently in the store, bound reader, and CLI. A silent read does not refresh the shared retention counters, so retention depends on writes and deliberate retention signals. Opted-in activity can still affect shared pruning.
- In the after run, the default arm must omit `record_access` so the harness exercises the new default. Success is 500/500 trials for rule 5 and rules 1–4. Preserve the explicit tracked arm for the applicable fault controls and verify that the ranking and hidden-channel faults still trigger separately. Implementation and the after run are pending.

## LongMemEval v3

- The [recorded v3 baseline](../experiments/results/longmemeval_v3.md) used 68 questions and 47 current-value questions. All three controls held. Across the six two-piece questions, lexical first hit@10 stayed 1.000 when updates were applied, while all required@10 fell from 1.000 to 0.167. Treat this as a result for that annotation snapshot and the whole-turn archive policy.
- The [reviewed annotations](../eval/longmemeval_knowledge_update_annotations_v3_reviewed.json) have 68 included questions, 45 current and five context. Eight of the original 11 former-evidence cases still require a turn that is superseded as the current value. Three proposed edges were removed from the update set: Silver eligibility vs Gold status, baseball counts from different windows, and Wednesday with Juan vs Thursday with Maria. The morning coffee update and required evidence now use the confirmation. The Apex update points to the explicit statement of the new current goal.
- The reviewed JSON preserves caution flags for ambiguous chronology, wording, and approximate answers. Use those flags when selecting detector controls or sensitivity cohorts. Remaining annotations are AI-derived. The reviewed cohort passed a conversion check. The corrected evaluation, detector run, and real-text cross-user dispute test are pending.

## Public project name

- The [expanded name check](public_name_review.md) identified another public agent context tool named MemVane and an existing registration for `memvane.com`. The GitHub repository was renamed to [ScopeSpool](https://github.com/hfarhidzadeh/scopespool) on 2026-11-24. The installed command and package currently use `memvane`.
