# Cross-user disputes on real text

LongMemEval_S user turns, reviewed v3 annotations; staged speakers; no LLM.
470 trials: 47 pairs from 45 current questions (47 supersedes edges, 0 dropped as identical text), 10 seeds each.
Store under test: schema version 7; injected fault: administrative.
See the docstring of `experiments/longmemeval_cross_user_disputes.py` for the design
and decision rule.

| Rule | Check | Held in | Needed | Holds |
| --- | --- | --- | --- | --- |
| 1 | Determinism: H and H2 identical | 470 of 470 (100.0%) | every trial | yes |
| 2 | Detection: W shows one open dispute, older vs newer, real text | 470 of 470 (100.0%) | every trial | yes |
| 3 | Power: V (visible hidden claims) differs from W | 470 of 470 (100.0%) | at least 50% | yes |
| 4 | A reply counts as knowing the newer claim | 297 of 470 (63.2%) | every trial | no |
| 5 | Presence alone is only access (bob, dana) | 146 of 470 (31.1%) | every trial | no |
| 6 | Noninterference: H equals W for every audience | 0 of 470 (0.0%) | every trial | no |

Verdict: **inconclusive (control 4, 5 failed)**

Reported, not part of the verdict:

- Hidden claims: 933; restating a visible text word for word: 624 of 933 (66.9%).
- In V the dispute was closed in 330 of 470 (70.2%) (in 330 of 330 (100.0%) of the trials with a claim by dana); statuses then shown: agrees, current, overruled.
- In W no dispute closed on its own: two members' claims of equal standing stayed disputed, whichever was said later.

Fault validation: rule 6 failed in 470 of 470 (100.0%); needed at least 25%: detected.

First noninterference failures:

- 0/0: alice (disputes); alice (who_knows); carol (disputes)
- 0/1: alice (disputes); alice (who_knows); carol (disputes)
- 0/2: alice (disputes); alice (who_knows); carol (disputes)
- 0/3: alice (disputes); alice (who_knows); carol (disputes)
- 0/4: alice (disputes); alice (who_knows); carol (disputes)
- 0/5: alice (disputes); alice (who_knows); carol (disputes)
- 0/6: alice (disputes); carol (disputes); alice+carol (disputes)
- 0/7: alice (disputes); alice (who_knows); carol (disputes)
- 0/8: alice (disputes); carol (disputes); alice+carol (disputes)
- 0/9: alice (disputes); alice (who_knows); carol (disputes)

Limits: who said which turn is staged; values are compared as exact text, so
paraphrased restatements are not tested.
