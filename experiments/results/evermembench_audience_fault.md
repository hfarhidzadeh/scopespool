# EverMemBench audience noninterference

Projects 01, 02, 03, 04, 05; 791 cross-group questions (0 skipped, no eligible asker); seed 0; lexical search, limit 10; injected fault: leak.
See the docstring of `experiments/evermembench_audience.py` for the design and rules.

Verdict: **leak (rules 3, 4 failed, first failing question F_SH_Top01_011)**

| Rule | Check | Held | Needed |
| --- | --- | --- | --- |
| 1 | Determinism (project 01 processed twice) | yes | equal |
| 2 | Power: POWER ranks hidden cited evidence in its top 10 | 354 of 791 (44.8%) | at least 25% |
| 3 | Noninterference: FULL equals VISIBLE | 0 of 791 (0.0%) | every question |
| 4 | No hidden-group message in FULL's top 10 | 62 of 791 (7.8%) | every question |

All-required@10 over the cited groups the asker can see: 0.034.

| Project | Questions | Skipped | Distinct askers |
| --- | ---: | ---: | ---: |
| 01 | 165 | 0 | 28 |
| 02 | 163 | 0 | 14 |
| 03 | 86 | 0 | 28 |
| 04 | 200 | 0 | 20 |
| 05 | 177 | 0 | 35 |

Fault validation: rule 3 failed in 791 of 791 (100.0%), rule 4 in 729 of 791 (92.2%); needed at least 25% each: detected.

Limits: the asker is staged, membership is inferred from who posted and is not dated, there is no roster, and group names only mean something within a project.

Python 3.9.6; sources: script `e48741869a8b`, store `40258276b32c`, loader `0193ed7f96ef`.
