# Zero leakage at no utility cost (H1), hard workload

Synthetic, scripted workspace with distractors that share query words, graded
relevance and audiences of one to three people; lexical search only; k = 10.
200 trials (seeds 0 to 199), with fault-swap-top in place of the built arm; 18488 utility, 1600 ceiling, 14304 leakage, 1800 owner and 7200
over-blocking items. See the hard section of the docstring of
`experiments/audience_utility.py` for the design and decision rule.

| Arm | Leaks | Owner hit@k | nDCG@10 | RR | recall@3 | hit@k | Mean shown |
| --- | --- | --- | --- | --- | --- | --- | --- |
| pooled (no access control) | 14304 (100.0%) | 1800 (100.0%) | 0.5040 | 0.5309 | 0.2206 | 93.7% | 10.00 |
| filter after, first k only | 0 (0.0%) | 1800 (100.0%) | 0.5989 | 0.6659 | 0.3732 | 93.7% | 6.13 |
| filter after, whole ranking | 0 (0.0%) | 1800 (100.0%) | 0.7151 | 0.6782 | 0.3851 | 99.7% | 9.96 |
| search with viewers (built) | 0 (0.0%) | 1800 (100.0%) | 0.6896 | 0.5923 | 0.3878 | 99.8% | 9.96 |
| fault: built without its rarest query word | n/a | n/a | 0.2470 | 0.2025 | 0.0670 | 75.8% | 9.77 |
| fault: built with its first two swapped | n/a | n/a | 0.6896 | 0.5923 | 0.3878 | 99.8% | 9.96 |

Differences: per-trial mean of the arm minus the other arm, 95% percentile
bootstrap CI over trials (2,000 resamples); sign test over trials, two-sided.

| Comparison | Role | Metric | Mean D | 95% CI | Trials + / = / - | Sign p | Items + / = / - | Reading |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| built minus after-all | rule 7 | nDCG@10 | -0.0254 | -0.0302 to -0.0210 | 43 / 0 / 157 | 1.9e-16 | 5521 / 3710 / 9257 | utility cost; difference detected |
| built minus after-all | rule 7 | RR | -0.0859 | -0.0999 to -0.0720 | 37 / 1 / 162 | 7.48e-20 | 3583 / 8109 / 6796 | utility cost; difference detected |
| built minus after-all | rule 7 | recall@3 | +0.0027 | +0.0001 to +0.0056 | 74 / 60 / 66 | 0.554 | 492 / 17615 / 381 | no utility cost; equal within the margin; difference detected |
| fault-drop-term minus after-all | rule 4 | nDCG@10 | -0.4681 | -0.4757 to -0.4605 | 0 / 0 / 200 | 1.24e-60 | 46 / 45 / 18397 | utility cost; difference detected |
| fault-drop-term minus after-all | rule 4 | RR | -0.4757 | -0.4885 to -0.4622 | 0 / 0 / 200 | 1.24e-60 | 25 / 995 / 17468 | utility cost; difference detected |
| fault-drop-term minus after-all | rule 4 | recall@3 | -0.3181 | -0.3273 to -0.3100 | 0 / 0 / 200 | 1.24e-60 | 28 / 1894 / 16566 | utility cost; difference detected |
| fault-swap-top minus after-all | rule 4 | nDCG@10 | -0.0254 | -0.0302 to -0.0210 | 43 / 0 / 157 | 1.9e-16 | 5521 / 3710 / 9257 | utility cost; difference detected |
| fault-swap-top minus after-all | rule 4 | RR | -0.0859 | -0.0999 to -0.0720 | 37 / 1 / 162 | 7.48e-20 | 3583 / 8109 / 6796 | utility cost; difference detected |
| fault-swap-top minus after-all | rule 4 | recall@3 | +0.0027 | +0.0001 to +0.0056 | 74 / 60 / 66 | 0.554 | 492 / 17615 / 381 | no utility cost; equal within the margin; difference detected |
| built minus after-k | descriptive | nDCG@10 | +0.0907 | +0.0836 to +0.0977 | 193 / 0 / 7 | 2.95e-48 | 11625 / 1701 / 5162 | no utility cost; difference detected |
| built minus after-k | descriptive | RR | -0.0736 | -0.0879 to -0.0593 | 49 / 1 / 150 | 4.16e-13 | 4461 / 7378 / 6649 | utility cost; difference detected |
| built minus after-k | descriptive | recall@3 | +0.0146 | +0.0111 to +0.0184 | 112 / 46 / 42 | 1.54e-08 | 910 / 17247 / 331 | no utility cost; difference detected |
| built minus pooled | descriptive | nDCG@10 | +0.1856 | +0.1761 to +0.1948 | 200 / 0 / 0 | 1.24e-60 | 14678 / 677 / 3133 | no utility cost; difference detected |
| built minus pooled | descriptive | RR | +0.0613 | +0.0431 to +0.0796 | 133 / 0 / 67 | 3.55e-06 | 9326 / 4605 / 4557 | no utility cost; difference detected |
| built minus pooled | descriptive | recall@3 | +0.1671 | +0.1573 to +0.1773 | 200 / 0 / 0 | 1.24e-60 | 8893 / 9574 / 21 | no utility cost; difference detected |

Built and after-all showed the same list in 51 of 18488 utility items (0.3%).
Ceiling (each focus pair, pooled, no audience, store-wide gold): mean RR 0.7229;
RR below 1.0 in 660 of 1600 items (41.2%); trial mean below 1.0 in 193 of 200 trials (96.5%).
After-all nDCG@10 below 1.0 in 18014 of 18488 utility items (97.4%).
Over-blocking: returned in 7200 of 7200 items, within the first k in 7200 (100.0%).
Determinism: seeds [0, 1, 2] rerun from scratch, identical: True.
Sanity: the largest store held 187 memories (BIG = 1000 covers every store: True);
write timestamps rose strictly in write order in 200 of 200 trials.

Decision:

- Rule 1, pooled leaks in at least 50% of leakage items: True (100.0%)
- Rule 1, owner hit@k in the built arm at least 95%: True (100.0%)
- Rule 2, every over-blocking item returned: True (0 missing)
- Rule 3, below the ceiling: True (trials True, ceiling items True, after-all items True)
- Rule 4, both planted faults read as a utility cost on nDCG@10: True (drop_term_minus_after_all True, swap_top_minus_after_all True)
- Rule 5, deterministic: True
- Rule 6, zero leakage in after-k, after-all and built: True
- Rule 7, built against after-all: nDCG@10 utility cost, RR utility cost, recall@3 no utility cost
- **Verdict: H1 not supported: rule 7, utility cost on nDCG@10 (built minus after-all -0.0254, 95% CI -0.0302 to -0.0210); rule 7, utility cost on RR (built minus after-all -0.0859, 95% CI -0.0999 to -0.0720)**

Limits: the data were written alongside the code. Grades come from the
generator, not from people. Only lexical search was tested (no embedder,
no links, no keys), and the audiences and channels are small.
