# EverMemBench audience noninterference

Projects 01, 02, 03, 04, 05; 791 cross-group questions (0 skipped, no eligible asker); seed 0; lexical search, limit 10.
See the docstring of `experiments/evermembench_audience.py` for the design and rules.

Verdict: **no leak across groups**

| Rule | Check | Held | Needed |
| --- | --- | --- | --- |
| 1 | Determinism (project 01 processed twice) | yes | equal |
| 2 | Power: POWER ranks hidden cited evidence in its top 10 | 354 of 791 (44.8%) | at least 25% |
| 3 | Noninterference: FULL equals VISIBLE | 791 of 791 (100.0%) | every question |
| 4 | No hidden-group message in FULL's top 10 | 791 of 791 (100.0%) | every question |

All-required@10 over the cited groups the asker can see: 0.059.

| Project | Questions | Skipped | Distinct askers |
| --- | ---: | ---: | ---: |
| 01 | 165 | 0 | 28 |
| 02 | 163 | 0 | 14 |
| 03 | 86 | 0 | 28 |
| 04 | 200 | 0 | 20 |
| 05 | 177 | 0 | 35 |

Limits: the asker is staged, membership is inferred from who posted and is not dated, there is no roster, and group names only mean something within a project.

Python 3.9.6; sources: script `e48741869a8b`, store `40258276b32c`, loader `0193ed7f96ef`.
