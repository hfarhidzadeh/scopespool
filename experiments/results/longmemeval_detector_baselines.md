# Update-detector baselines on LongMemEval (version 3, reviewed annotations; provisional)

Real LongMemEval text; no LLM. 68 questions (53 positives with a `supersedes` edge, 15 negatives); MiniLM backend: sentence-transformers.
Annotations: `eval/longmemeval_knowledge_update_annotations_v3_reviewed.json` (sha256 44dc0791aa1bc551); data sha256 d6f21ea9d60a0d56.
Ground truth is the researcher's five category decisions plus a source-evidence review whose reviewer is not recorded; the rest is AI-derived, not human-adjudicated.
See the docstring of `experiments/longmemeval_detector_baselines.py` for the design and rule.

## Controls

- C1 (`never` equals no updates and fires 0 times): True
- C2 (`oracle-cand` is right exactly where a true target is a candidate, and matches the oracle there): True

**Verdict: overlap: not usable (a, b, e); hash: not usable (a, b, c, d, e); minilm: not usable (a, b, c, d, e)**

Candidate recall (a true old turn among the 5 candidates): 51 of 55 old turns; 51 of 53 positive questions.

## Detectors at their shipped defaults

| Detector | Positives: fired / correct / wrong | Current recall | Negatives fired | Control turns fired | Recovery of oracle RR gain | Conditions failed |
| --- | --- | --- | --- | --- | --- | --- |
| overlap | 0 / 0 / 0 of 53 | 0.000 (0 of 45) | 0 of 15 | 14 of 680 | 0.00 | a; b; e |
| hash | 31 / 12 / 19 of 53 | 0.244 (11 of 45) | 6 of 15 | 162 of 680 | 0.42 | a; b; c; d; e |
| minilm | 28 / 9 / 19 of 53 | 0.200 (9 of 45) | 8 of 15 | 249 of 680 | 0.35 | a; b; c; d; e |
| top | 53 / 25 / 28 of 53 | 0.511 (23 of 45) | 15 of 15 | 679 of 680 | 0.84 | - |
| never | 0 / 0 / 0 of 53 | 0.000 (0 of 45) | 0 of 15 | 0 of 680 | 0.00 | - |
| oracle-cand | 51 / 51 / 0 of 53 | 1.000 (45 of 45) | 0 of 15 | 0 of 680 | 1.00 | - |

Condition letters: a recall, b beats random, c control-turn fire rate, d negative fire rate, e recovery.

## Recall against random (current positives, correct minus expected-by-chance)

- overlap: -0.200 (95% -0.200 to -0.200, p 0.000; 0 better, 45 worse, n 45)
- hash: +0.044 (95% -0.067 to +0.178, p 0.540; 11 better, 34 worse, n 45)
- minilm: +0.000 (95% -0.111 to +0.111, p 1.000; 9 better, 36 worse, n 45)
- top: +0.311 (95% +0.156 to +0.467, p 0.000; 23 better, 22 worse, n 45)

## End to end, current cohort (reciprocal rank of the first required turn, depth 10)

- Oracle gain over no updates: +0.153 (95% +0.093 to +0.220, p 0.000; 20 better, 1 worse, n 45)
- overlap gain over no updates: +0.000 (95% +0.000 to +0.000, p 1.000; 0 better, 0 worse, n 45)
- hash gain over no updates: +0.065 (95% +0.023 to +0.115, p 0.004; 9 better, 0 worse, n 45)
- minilm gain over no updates: +0.054 (95% +0.016 to +0.099, p 0.008; 8 better, 0 worse, n 45)
- top gain over no updates: +0.128 (95% +0.073 to +0.187, p 0.000; 18 better, 0 worse, n 45)

## Retrieval by cohort (mean over questions)

| Arm | Cohort | n | RR | all required@10 |
| --- | --- | --- | --- | --- |
| none | current | 45 | 0.535 | 0.956 |
| none | previous | 9 | 0.398 | 0.889 |
| none | both | 6 | 0.833 | 1.000 |
| none | latest_event | 3 | 0.667 | 0.667 |
| none | context | 5 | 0.600 | 1.000 |
| none | all | 68 | 0.554 | 0.941 |
| oracle | current | 45 | 0.688 | 0.956 |
| oracle | previous | 9 | 0.278 | 0.556 |
| oracle | both | 6 | 0.694 | 0.167 |
| oracle | latest_event | 3 | 0.667 | 0.667 |
| oracle | context | 5 | 0.600 | 1.000 |
| oracle | all | 68 | 0.627 | 0.824 |
| overlap | current | 45 | 0.535 | 0.956 |
| overlap | previous | 9 | 0.398 | 0.889 |
| overlap | both | 6 | 0.833 | 1.000 |
| overlap | latest_event | 3 | 0.667 | 0.667 |
| overlap | context | 5 | 0.600 | 1.000 |
| overlap | all | 68 | 0.554 | 0.941 |
| hash | current | 45 | 0.600 | 0.956 |
| hash | previous | 9 | 0.454 | 0.889 |
| hash | both | 6 | 0.917 | 0.833 |
| hash | latest_event | 3 | 0.500 | 0.667 |
| hash | context | 5 | 0.800 | 1.000 |
| hash | all | 68 | 0.619 | 0.926 |
| minilm | current | 45 | 0.589 | 0.956 |
| minilm | previous | 9 | 0.398 | 0.778 |
| minilm | both | 6 | 0.833 | 1.000 |
| minilm | latest_event | 3 | 0.500 | 0.667 |
| minilm | context | 5 | 0.700 | 1.000 |
| minilm | all | 68 | 0.589 | 0.926 |
| top | current | 45 | 0.663 | 0.956 |
| top | previous | 9 | 0.306 | 0.556 |
| top | both | 6 | 0.917 | 0.500 |
| top | latest_event | 3 | 0.500 | 0.667 |
| top | context | 5 | 0.900 | 1.000 |
| top | all | 68 | 0.648 | 0.853 |
| random | current | 45 | 0.576 | 0.956 |
| random | previous | 9 | 0.356 | 0.744 |
| random | both | 6 | 0.858 | 0.850 |
| random | latest_event | 3 | 0.617 | 0.667 |
| random | context | 5 | 0.690 | 1.000 |
| random | all | 68 | 0.582 | 0.909 |

## Threshold sweep (reported, not part of the verdict)

| Detector | Threshold | Current recall | Wrong target (positives) | Negatives fired | Control turns fired |
| --- | --- | --- | --- | --- | --- |
| overlap | 0.2 | 0.289 | 17 | 5 | 191 of 680 |
| overlap | 0.3 | 0.111 | 7 | 0 | 67 of 680 |
| overlap | 0.4 | 0.067 | 2 | 0 | 23 of 680 |
| overlap | 0.5 | 0.000 | 0 | 0 | 14 of 680 |
| overlap | 0.6 | 0.000 | 0 | 0 | 6 of 680 |
| hash | 0.4 | 0.378 | 35 | 15 | 563 of 680 |
| hash | 0.5 | 0.378 | 33 | 15 | 389 of 680 |
| hash | 0.6 | 0.244 | 19 | 6 | 162 of 680 |
| hash | 0.7 | 0.089 | 5 | 0 | 51 of 680 |
| hash | 0.8 | 0.000 | 1 | 0 | 10 of 680 |
| minilm | 0.4 | 0.333 | 31 | 14 | 431 of 680 |
| minilm | 0.5 | 0.267 | 29 | 9 | 354 of 680 |
| minilm | 0.6 | 0.200 | 19 | 8 | 249 of 680 |
| minilm | 0.7 | 0.133 | 11 | 2 | 149 of 680 |
| minilm | 0.8 | 0.089 | 5 | 0 | 50 of 680 |

Limits: the annotations are provisional; candidates come from BM25 over the whole store filtered to earlier turns; only the decision for the new turn is applied, so control-turn fires are counted but their harm is not measured; a control-turn fire may be a genuine unlabelled update, so that rate is an upper bound; baselines are simple by design and a model-based detector is not tested here.
