# The record_access side channel

Synthetic, scripted data; no LLM. 100 trials (seeds 0 to 99); 8 topics, chance 12.5%.
Store under test: schema version 7; injected fault: popularity-boost.
See the docstring of `experiments/audience_access_channel.py` for the design and rule.

| Rule | Check | Held in | Needed | Holds |
| --- | --- | --- | --- | --- |
| 1 | Determinism: the same seed gives the same result (control) | 100 of 100 (100.0%, 95% interval 96.3 to 100.0%) | every trial | True |
| 2 | Observer control: with a silent read or none, the observer sees no change (control) | 100 of 100 (100.0%, 95% interval 96.3 to 100.0%) | every trial | True |
| 3 | Ranking: another member's ranked results are unchanged by a read | 0 of 100 (0.0%, 95% interval 0.0 to 3.7%) | every trial | False |
| 4 | Hidden: a member of another channel sees no change; nothing outside the channel changes | 100 of 100 (100.0%, 95% interval 96.3 to 100.0%) | every trial | True |
| 5 | Trace: another member of the channel sees no change after a read | 0 of 100 (0.0%, 95% interval 0.0 to 3.7%) | every trial | False |

**Verdict: a read changes what others can observe beyond the memories it returned (rules 3 failed, first failing seed 0)**

Reported, not part of the verdict (the observer is bob, a member of `team` who did not read):

- Sees that someone read, from the counters: 100 of 100 (100.0%, 95% interval 96.3 to 100.0%); from the survivors of a later prune: 100 of 100 (100.0%, 95% interval 96.3 to 100.0%).
- Names alice's topic from the counters: 100 of 100 (100.0%, 95% interval 96.3 to 100.0%); from the prune survivors: 100 of 100 (100.0%, 95% interval 96.3 to 100.0%).
- Changed set equals exactly the returned memories bob can see: 100 of 100 (100.0%, 95% interval 96.3 to 100.0%).
- Sees the read's time (last_accessed_at on every changed memory): 100 of 100 (100.0%, 95% interval 96.3 to 100.0%).

Limits: one reader, one query, and unique topic tokens, which is the easy case for an observer; real reads are noisier but leave the same counters. The counters belong to the memory, so every member who can see it sees them. A read with `record_access=False` (the CLI's `--peek`) leaves no trace in this experiment. No mitigation is built or tested here.

Validation: rule 3 failed in 100 of 100 trials (100.0%): detected.
