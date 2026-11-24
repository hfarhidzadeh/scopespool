# LongMemEval knowledge updates, version 3 (provisional)

Real LongMemEval text; no LLM. 68 questions annotated for required evidence and supersession; semantic backend: sentence-transformers.
Annotations are AI-derived and not human-adjudicated; results are not comparable with versions 1 and 2.
Data sha256 d6f21ea9d60a0d56; annotations sha256 78e8c466638d357b.
See the docstring of `experiments/longmemeval_v3.py` for the design and decision rule.

## Controls

- C1 (no supersession edge: applying updates changes nothing): True
- C2 (archiving every required turn takes all required@10 to 0): True
- C3 (archiving random non-required turns moves the mean by less than 0.02): True (shift: lexical 0.0000, semantic 0.0000)

**Verdict: lexical: applying supersession, current-value questions: no clear effect; questions that need the old evidence: hurts; semantic: applying supersession, current-value questions: no clear effect; questions that need the old evidence: hurts; semantic vs lexical: no clear effect**

## Readings (change in all required@10)

- A. Applying supersession to the 47 current-value questions, lexical: +0.000 (95% +0.000 to +0.000, p 1.000; 0 better, 0 worse, 47 same, n 47)
- A. Same, semantic: +0.000 (95% +0.000 to +0.000, p 1.000; 0 better, 0 worse, 47 same, n 47)
- A' (not in the verdict), reciprocal rank on the current-value questions: lexical +0.157 (95% +0.096 to +0.223, p 0.000; 21 better, 1 worse, 25 same, n 47); semantic +0.145 (95% +0.092 to +0.205, p 0.000; 32 better, 2 worse, 13 same, n 47)
- A' (not in the verdict), stale-first on the current-value questions: lexical -0.468 (95% -0.617 to -0.319, p 0.000; 0 better, 22 worse, 25 same, n 47); semantic -0.638 (95% -0.766 to -0.511, p 0.000; 0 better, 30 worse, 17 same, n 47)
- B. Applying supersession to the 11 questions that need the old evidence, lexical: -1.000 (95% -1.000 to -1.000, p 0.001; 0 better, 11 worse, 0 same, n 11)
- B. Same, semantic: -0.909 (95% -1.000 to -0.727, p 0.002; 0 better, 10 worse, 1 same, n 11)
- C. Semantic minus lexical, updates kept, all 68 questions: +0.044 (95% -0.015 to +0.118, p 0.375; 4 better, 1 worse, 63 same, n 68)
- C. Same, the 6 questions needing two pieces: -0.167 (95% -0.500 to +0.000, p 1.000; 0 better, 1 worse, 5 same, n 6)

## Cohorts (depth 10)

| Configuration | Cohort | n | first hit@10 | all required@10 | group coverage | RR | stale first |
| --- | --- | --- | --- | --- | --- | --- | --- |
| lexical/kept | current | 47 | 0.957 | 0.957 | 0.957 | 0.533 | 0.468 |
| lexical/kept | previous | 9 | 0.889 | 0.889 | 0.889 | 0.398 | - |
| lexical/kept | both | 6 | 1.000 | 1.000 | 1.000 | 0.833 | - |
| lexical/kept | latest_event | 3 | 0.667 | 0.667 | 0.667 | 0.667 | - |
| lexical/kept | context | 3 | 1.000 | 1.000 | 1.000 | 0.667 | - |
| lexical/kept | all | 68 | 0.941 | 0.941 | 0.941 | 0.554 | 0.468 |
| lexical/applied | current | 47 | 0.957 | 0.957 | 0.957 | 0.690 | 0.000 |
| lexical/applied | previous | 9 | 0.222 | 0.222 | 0.222 | 0.111 | - |
| lexical/applied | both | 6 | 1.000 | 0.167 | 0.583 | 0.694 | - |
| lexical/applied | latest_event | 3 | 0.667 | 0.667 | 0.667 | 0.667 | - |
| lexical/applied | context | 3 | 1.000 | 1.000 | 1.000 | 0.667 | - |
| lexical/applied | all | 68 | 0.853 | 0.779 | 0.816 | 0.612 | 0.000 |
| semantic/kept | current | 47 | 1.000 | 1.000 | 1.000 | 0.380 | 0.638 |
| semantic/kept | previous | 9 | 1.000 | 1.000 | 1.000 | 0.306 | - |
| semantic/kept | both | 6 | 1.000 | 0.833 | 0.917 | 0.694 | - |
| semantic/kept | latest_event | 3 | 1.000 | 1.000 | 1.000 | 0.400 | - |
| semantic/kept | context | 3 | 1.000 | 1.000 | 1.000 | 0.344 | - |
| semantic/kept | all | 68 | 1.000 | 0.985 | 0.993 | 0.397 | 0.638 |
| semantic/applied | current | 47 | 1.000 | 1.000 | 1.000 | 0.524 | 0.000 |
| semantic/applied | previous | 9 | 0.333 | 0.333 | 0.333 | 0.093 | - |
| semantic/applied | both | 6 | 0.833 | 0.167 | 0.500 | 0.500 | - |
| semantic/applied | latest_event | 3 | 1.000 | 1.000 | 1.000 | 0.400 | - |
| semantic/applied | context | 3 | 1.000 | 1.000 | 1.000 | 0.344 | - |
| semantic/applied | all | 68 | 0.897 | 0.838 | 0.868 | 0.452 | 0.000 |

## Sensitivity: the 5 contested questions dropped (64 questions)

- A, lexical: +0.000 (95% +0.000 to +0.000, p 1.000; 0 better, 0 worse, 45 same, n 45); semantic: +0.000 (95% +0.000 to +0.000, p 1.000; 0 better, 0 worse, 45 same, n 45)
- B, lexical: -1.000 (95% -1.000 to -1.000, p 0.001; 0 better, 11 worse, 0 same, n 11); semantic: -0.909 (95% -1.000 to -0.727, p 0.002; 0 better, 10 worse, 1 same, n 11)
- C: +0.047 (95% -0.016 to +0.109, p 0.375; 4 better, 1 worse, 59 same, n 64)

Limits: the annotations are provisional and only 6 questions need two pieces of evidence; links are session links only; updates are an oracle (perfect detection), so the applied configuration shows the best case and the harm of archiving needed evidence, not what a detector would do. The whole-turn archive policy is an experimental intervention.
