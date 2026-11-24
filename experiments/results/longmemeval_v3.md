# LongMemEval knowledge updates, version 3 (provisional)

Real LongMemEval text; no LLM. 68 questions annotated for required evidence and supersession; semantic backend: sentence-transformers.
Annotations: the researcher's five category decisions plus a source-evidence review whose reviewer is not recorded; the rest is AI-derived and not human-adjudicated. Not comparable with versions 1 and 2.
Annotations: `eval/longmemeval_knowledge_update_annotations_v3_reviewed.json`. Data sha256 d6f21ea9d60a0d56; annotations sha256 44dc0791aa1bc551.
See the docstring of `experiments/longmemeval_v3.py` for the design and decision rule.

## Controls

- C1 (no supersession edge: applying updates changes nothing): True
- C2 (archiving every required turn takes all required@10 to 0): True
- C3 (archiving random non-required turns moves the mean by less than 0.02): True (shift: lexical 0.0000, semantic 0.0000)

**Verdict: lexical: applying supersession, current-value questions: no clear effect; questions that need the old evidence: hurts; semantic: applying supersession, current-value questions: no clear effect; questions that need the old evidence: hurts; semantic vs lexical: no clear effect**

## Readings (change in all required@10)

- A. Applying supersession to the 45 current-value questions, lexical: +0.000 (95% +0.000 to +0.000, p 1.000; 0 better, 0 worse, 45 same, n 45)
- A. Same, semantic: +0.000 (95% +0.000 to +0.000, p 1.000; 0 better, 0 worse, 45 same, n 45)
- A' (not in the verdict), reciprocal rank on the current-value questions: lexical +0.153 (95% +0.093 to +0.220, p 0.000; 20 better, 1 worse, 24 same, n 45); semantic +0.140 (95% +0.087 to +0.200, p 0.000; 31 better, 2 worse, 12 same, n 45)
- A' (not in the verdict), stale-first on the current-value questions: lexical -0.467 (95% -0.622 to -0.311, p 0.000; 0 better, 21 worse, 24 same, n 45); semantic -0.644 (95% -0.778 to -0.511, p 0.000; 0 better, 29 worse, 16 same, n 45)
- B. Applying supersession to the 8 questions that need the old evidence, lexical: -1.000 (95% -1.000 to -1.000, p 0.008; 0 better, 8 worse, 0 same, n 8)
- B. Same, semantic: -0.875 (95% -1.000 to -0.625, p 0.016; 0 better, 7 worse, 1 same, n 8)
- C. Semantic minus lexical, updates kept, all 68 questions: +0.044 (95% -0.015 to +0.118, p 0.375; 4 better, 1 worse, 63 same, n 68)
- C. Same, the 6 questions needing two pieces: -0.167 (95% -0.500 to +0.000, p 1.000; 0 better, 1 worse, 5 same, n 6)

## Cohorts (depth 10)

| Configuration | Cohort | n | first hit@10 | all required@10 | group coverage | RR | stale first |
| --- | --- | --- | --- | --- | --- | --- | --- |
| lexical/kept | current | 45 | 0.956 | 0.956 | 0.956 | 0.535 | 0.467 |
| lexical/kept | previous | 9 | 0.889 | 0.889 | 0.889 | 0.398 | - |
| lexical/kept | both | 6 | 1.000 | 1.000 | 1.000 | 0.833 | - |
| lexical/kept | latest_event | 3 | 0.667 | 0.667 | 0.667 | 0.667 | - |
| lexical/kept | context | 5 | 1.000 | 1.000 | 1.000 | 0.600 | - |
| lexical/kept | all | 68 | 0.941 | 0.941 | 0.941 | 0.554 | 0.467 |
| lexical/applied | current | 45 | 0.956 | 0.956 | 0.956 | 0.688 | 0.000 |
| lexical/applied | previous | 9 | 0.556 | 0.556 | 0.556 | 0.278 | - |
| lexical/applied | both | 6 | 1.000 | 0.167 | 0.583 | 0.694 | - |
| lexical/applied | latest_event | 3 | 0.667 | 0.667 | 0.667 | 0.667 | - |
| lexical/applied | context | 5 | 1.000 | 1.000 | 1.000 | 0.600 | - |
| lexical/applied | all | 68 | 0.897 | 0.824 | 0.860 | 0.627 | 0.000 |
| semantic/kept | current | 45 | 1.000 | 1.000 | 1.000 | 0.374 | 0.644 |
| semantic/kept | previous | 9 | 1.000 | 1.000 | 1.000 | 0.306 | - |
| semantic/kept | both | 6 | 1.000 | 0.833 | 0.917 | 0.611 | - |
| semantic/kept | latest_event | 3 | 1.000 | 1.000 | 1.000 | 0.400 | - |
| semantic/kept | context | 5 | 1.000 | 1.000 | 1.000 | 0.407 | - |
| semantic/kept | all | 68 | 1.000 | 0.985 | 0.993 | 0.390 | 0.644 |
| semantic/applied | current | 45 | 1.000 | 1.000 | 1.000 | 0.514 | 0.000 |
| semantic/applied | previous | 9 | 0.667 | 0.667 | 0.667 | 0.241 | - |
| semantic/applied | both | 6 | 0.833 | 0.167 | 0.500 | 0.417 | - |
| semantic/applied | latest_event | 3 | 1.000 | 1.000 | 1.000 | 0.400 | - |
| semantic/applied | context | 5 | 1.000 | 1.000 | 1.000 | 0.407 | - |
| semantic/applied | all | 68 | 0.941 | 0.882 | 0.912 | 0.457 | 0.000 |

## Sensitivity: the 5 contested questions dropped (64 questions)

- A, lexical: +0.000 (95% +0.000 to +0.000, p 1.000; 0 better, 0 worse, 45 same, n 45); semantic: +0.000 (95% +0.000 to +0.000, p 1.000; 0 better, 0 worse, 45 same, n 45)
- B, lexical: -1.000 (95% -1.000 to -1.000, p 0.008; 0 better, 8 worse, 0 same, n 8); semantic: -0.875 (95% -1.000 to -0.625, p 0.016; 0 better, 7 worse, 1 same, n 8)
- C: +0.047 (95% -0.016 to +0.109, p 0.375; 4 better, 1 worse, 59 same, n 64)

Limits: the annotations are provisional and only 6 questions need two pieces of evidence; links are session links only; updates are an oracle (perfect detection), so the applied configuration shows the best case and the harm of archiving needed evidence, not what a detector would do. The whole-turn archive policy is an experimental intervention.
