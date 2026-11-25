# LongMemEval knowledge updates, version 3 (provisional)

Real LongMemEval text; no LLM. 64 questions annotated for required evidence and supersession; semantic backend: sentence-transformers.
The project owner accepted 9 proposed category decisions on 2026-11-25; remaining required-evidence groups and update relations are provisional and partly AI-derived. Not comparable with versions 1 and 2.
Annotations: `longmemeval_knowledge_update_annotations_v3_category_approved_2026-11-25.json`. Data sha256 d6f21ea9d60a0d56; annotations sha256 a2b75e3795557b9a.
See the docstring of `experiments/longmemeval_v3.py` for the design and decision rule.

## Controls

- C1 (no supersession edge: applying updates changes nothing): True
- C2 (archiving every required turn takes all required@10 to 0): True
- C3 (archiving random non-required turns moves the mean by less than 0.02): True (shift: lexical 0.0000, semantic 0.0000)

**Verdict: lexical: applying supersession, current-value questions: no clear effect; questions that need the old evidence: hurts; semantic: applying supersession, current-value questions: no clear effect; questions that need the old evidence: hurts; semantic vs lexical: no clear effect**

## Readings (change in all required@10)

- A. Applying supersession to the 44 current-value questions, lexical: +0.000 (95% +0.000 to +0.000, p 1.000; 0 better, 0 worse, 44 same, n 44)
- A. Same, semantic: +0.000 (95% +0.000 to +0.000, p 1.000; 0 better, 0 worse, 44 same, n 44)
- A' (not in the verdict), reciprocal rank on the current-value questions: lexical +0.156 (95% +0.093 to +0.225, p 0.000; 20 better, 1 worse, 23 same, n 44); semantic +0.140 (95% +0.086 to +0.200, p 0.000; 30 better, 2 worse, 12 same, n 44)
- A' (not in the verdict), stale-first on the current-value questions: lexical -0.477 (95% -0.636 to -0.341, p 0.000; 0 better, 21 worse, 23 same, n 44); semantic -0.659 (95% -0.795 to -0.523, p 0.000; 0 better, 29 worse, 15 same, n 44)
- B. Applying supersession to the 7 questions that need the old evidence, lexical: -1.000 (95% -1.000 to -1.000, p 0.016; 0 better, 7 worse, 0 same, n 7)
- B. Same, semantic: -0.857 (95% -1.000 to -0.571, p 0.031; 0 better, 6 worse, 1 same, n 7)
- C. Semantic minus lexical, updates kept, all 64 questions: +0.031 (95% -0.031 to +0.094, p 0.625; 3 better, 1 worse, 60 same, n 64)
- C. Same, the 6 questions needing two pieces: -0.167 (95% -0.500 to +0.000, p 1.000; 0 better, 1 worse, 5 same, n 6)

## Cohorts (depth 10)

| Configuration | Cohort | n | first hit@10 | all required@10 | group coverage | RR | stale first |
| --- | --- | --- | --- | --- | --- | --- | --- |
| lexical/kept | current | 44 | 0.955 | 0.955 | 0.955 | 0.524 | 0.477 |
| lexical/kept | previous | 7 | 1.000 | 1.000 | 1.000 | 0.440 | - |
| lexical/kept | both | 6 | 1.000 | 1.000 | 1.000 | 0.833 | - |
| lexical/kept | latest_event | 2 | 0.500 | 0.500 | 0.500 | 0.500 | - |
| lexical/kept | context | 5 | 1.000 | 1.000 | 1.000 | 0.600 | - |
| lexical/kept | all | 64 | 0.953 | 0.953 | 0.953 | 0.549 | 0.477 |
| lexical/applied | current | 44 | 0.955 | 0.955 | 0.955 | 0.681 | 0.000 |
| lexical/applied | previous | 7 | 0.714 | 0.714 | 0.714 | 0.321 | - |
| lexical/applied | both | 6 | 1.000 | 0.167 | 0.583 | 0.694 | - |
| lexical/applied | latest_event | 2 | 0.500 | 0.500 | 0.500 | 0.500 | - |
| lexical/applied | context | 5 | 1.000 | 1.000 | 1.000 | 0.600 | - |
| lexical/applied | all | 64 | 0.922 | 0.844 | 0.883 | 0.631 | 0.000 |
| semantic/kept | current | 44 | 1.000 | 1.000 | 1.000 | 0.375 | 0.659 |
| semantic/kept | previous | 7 | 1.000 | 1.000 | 1.000 | 0.298 | - |
| semantic/kept | both | 6 | 1.000 | 0.833 | 0.917 | 0.611 | - |
| semantic/kept | latest_event | 2 | 1.000 | 1.000 | 1.000 | 0.350 | - |
| semantic/kept | context | 5 | 1.000 | 1.000 | 1.000 | 0.407 | - |
| semantic/kept | all | 64 | 1.000 | 0.984 | 0.992 | 0.391 | 0.659 |
| semantic/applied | current | 44 | 1.000 | 1.000 | 1.000 | 0.515 | 0.000 |
| semantic/applied | previous | 7 | 0.714 | 0.714 | 0.714 | 0.250 | - |
| semantic/applied | both | 6 | 0.833 | 0.167 | 0.500 | 0.417 | - |
| semantic/applied | latest_event | 2 | 1.000 | 1.000 | 1.000 | 0.350 | - |
| semantic/applied | context | 5 | 1.000 | 1.000 | 1.000 | 0.407 | - |
| semantic/applied | all | 64 | 0.953 | 0.891 | 0.922 | 0.463 | 0.000 |

## Sensitivity: the five originally disputed IDs omitted (60 questions)

- A, lexical: +0.000 (95% +0.000 to +0.000, p 1.000; 0 better, 0 worse, 44 same, n 44); semantic: +0.000 (95% +0.000 to +0.000, p 1.000; 0 better, 0 worse, 44 same, n 44)
- B, lexical: -1.000 (95% -1.000 to -1.000, p 0.016; 0 better, 7 worse, 0 same, n 7); semantic: -0.857 (95% -1.000 to -0.571, p 0.031; 0 better, 6 worse, 1 same, n 7)
- C: +0.033 (95% -0.033 to +0.100, p 0.625; 3 better, 1 worse, 56 same, n 60)

Limits: the annotations are provisional and only 6 questions need two pieces of evidence; links are session links only; updates are an oracle (perfect detection), so the applied configuration shows the best case and the harm of archiving needed evidence, not what a detector would do. The whole-turn archive policy is an experimental intervention.
