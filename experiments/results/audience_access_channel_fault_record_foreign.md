# The record_access side channel

Synthetic, scripted data; no LLM. 100 trials (seeds 0 to 99); 8 topics, chance 12.5%.
Store under test: schema version 7; injected fault: record-foreign.
See the docstring of `experiments/audience_access_channel.py` for the design and rule.

| Rule | Check | Held in | Needed | Holds |
| --- | --- | --- | --- | --- |
| 1 | Determinism: the same seed gives the same result (control) | 100 of 100 (100.0%, 95% interval 96.3 to 100.0%) | every trial | True |
| 2 | Observer control: with a silent read or none, the observer sees no change (control) | 100 of 100 (100.0%, 95% interval 96.3 to 100.0%) | every trial | True |
| 3 | Ranking: another member's ranked results are unchanged by a read | 100 of 100 (100.0%, 95% interval 96.3 to 100.0%) | every trial | True |
| 4 | Hidden: a member of another channel sees no change; nothing outside the channel changes | 0 of 100 (0.0%, 95% interval 0.0 to 3.7%) | every trial | False |
| 5 | Trace: another member of the channel sees no change after a read | 0 of 100 (0.0%, 95% interval 0.0 to 3.7%) | every trial | False |

**Verdict: a read changes what others can observe beyond the memories it returned (rules 4 failed, first failing seed 0)**

Reported, not part of the verdict (the observer is bob, a member of `team` who did not read):

- Default read (`record_access` left out). Sees that someone read, from the counters: 100 of 100 (100.0%, 95% interval 96.3 to 100.0%); from the survivors of a later prune: 100 of 100 (100.0%, 95% interval 96.3 to 100.0%). Names alice's topic from the counters: 100 of 100 (100.0%, 95% interval 96.3 to 100.0%); from the survivors: 100 of 100 (100.0%, 95% interval 96.3 to 100.0%).
- Opt-in read (`record_access=True`). Sees that someone read, from the counters: 100 of 100 (100.0%, 95% interval 96.3 to 100.0%); from the survivors: 100 of 100 (100.0%, 95% interval 96.3 to 100.0%). Names alice's topic from the counters: 100 of 100 (100.0%, 95% interval 96.3 to 100.0%); from the survivors: 100 of 100 (100.0%, 95% interval 96.3 to 100.0%).
- Opt-in: changed set equals exactly the returned memories bob can see: 0 of 100 (0.0%, 95% interval 0.0 to 3.7%); shows the read's time (last_accessed_at on every changed memory): 100 of 100 (100.0%, 95% interval 96.3 to 100.0%).

Limits: one reader, one query, and unique topic tokens, which is the easy case for an observer. The counters belong to the memory, so a reader who opts in with `record_access=True` (the CLI's `--record`) still tells every member who can see it what they looked up; the server does not let members opt in. With the default, reads for named viewers no longer count as accesses, so they no longer keep a memory from being pruned; retention then depends on reads without viewers, or on opted-in reads.

Validation: rule 4 failed in 100 of 100 trials (100.0%): detected.
