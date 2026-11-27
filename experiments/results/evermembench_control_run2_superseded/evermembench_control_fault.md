# EverMemBench loader control

**Fault detected**: rule `token-only`; injected fault `off-by-one`; lexical all-required@10 0 of 444 eligible questions (0.000); unplanted token hits 0.

Criterion: For every question with at most ten R entries, the token-only query's lexical top 10 covers every R entry; an unplanted token returns zero results.

Run 1 (rule `original`, superseded): 117 of 2212 (0.053), failed; see `experiments/results/evermembench_control_run1_superseded/evermembench_control.json`. The rule was changed on 2026-11-26 before this run; the docstring of `experiments/evermembench_control.py` records the deviation.

| Topic | Messages | Questions | Eligible | Over ten entries | All required | Failed | Unplanted hits |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 01 | 10,222 | 488 | 444 | 44 | 0 | 444 | 0 |

Dataset EverMind-AI/EverMemBench-Dynamic at revision `a6b210a32248e841967b7b64a64281d2ff3f669d`; inputs and code pinned by SHA-256 in the JSON report. Python 3.14.8.
