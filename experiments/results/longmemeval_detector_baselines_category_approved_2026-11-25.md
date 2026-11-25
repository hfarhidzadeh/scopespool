# Update-detector baselines on LongMemEval (version 3, reviewed annotations; provisional)

Real LongMemEval text; no LLM. 64 questions (51 positives with a `supersedes` edge, 13 negatives); MiniLM backend: sentence-transformers.
Annotations: `longmemeval_knowledge_update_annotations_v3_category_approved_2026-11-25.json` (sha256 a2b75e3795557b9a); data sha256 d6f21ea9d60a0d56.
The project owner accepted 9 proposed category decisions on 2026-11-25; remaining required-evidence groups and update relations are provisional and partly AI-derived.
See the docstring of `experiments/longmemeval_detector_baselines.py` for the design and rule.

## Controls

- C1 (`never` equals no updates and fires 0 times): True
- C2 (`oracle-cand` is right exactly where a true target is a candidate, and matches the oracle there): True

**Verdict: overlap: not usable (a, b, e); hash: not usable (a, b, c, d, e); minilm: not usable (a, b, c, d, e)**

Candidate recall (a true old turn among the 5 candidates): 49 of 53 old turns; 49 of 51 positive questions.

## Detectors at their shipped defaults

| Detector | Positives: fired / correct / wrong | Current recall | Negatives fired | Control turns fired | Recovery of oracle RR gain | Conditions failed |
| --- | --- | --- | --- | --- | --- | --- |
| overlap | 0 / 0 / 0 of 51 | 0.000 (0 of 44) | 0 of 13 | 14 of 640 | 0.00 | a; b; e |
| hash | 31 / 12 / 19 of 51 | 0.250 (11 of 44) | 5 of 13 | 155 of 640 | 0.42 | a; b; c; d; e |
| minilm | 27 / 9 / 18 of 51 | 0.205 (9 of 44) | 7 of 13 | 236 of 640 | 0.35 | a; b; c; d; e |
| top | 51 / 25 / 26 of 51 | 0.523 (23 of 44) | 13 of 13 | 639 of 640 | 0.84 | - |
| never | 0 / 0 / 0 of 51 | 0.000 (0 of 44) | 0 of 13 | 0 of 640 | 0.00 | - |
| oracle-cand | 49 / 49 / 0 of 51 | 1.000 (44 of 44) | 0 of 13 | 0 of 640 | 1.00 | - |

Condition letters: a recall, b beats random, c control-turn fire rate, d negative fire rate, e recovery.

## Recall against random (current positives, correct minus expected-by-chance)

- overlap: -0.200 (95% -0.200 to -0.200, p 0.000; 0 better, 44 worse, n 44)
- hash: +0.050 (95% -0.064 to +0.186, p 0.498; 11 better, 33 worse, n 44)
- minilm: +0.005 (95% -0.109 to +0.118, p 1.000; 9 better, 35 worse, n 44)
- top: +0.323 (95% +0.164 to +0.459, p 0.000; 23 better, 21 worse, n 44)

## End to end, current cohort (reciprocal rank of the first required turn, depth 10)

- Oracle gain over no updates: +0.156 (95% +0.093 to +0.225, p 0.000; 20 better, 1 worse, n 44)
- overlap gain over no updates: +0.000 (95% +0.000 to +0.000, p 1.000; 0 better, 0 worse, n 44)
- hash gain over no updates: +0.066 (95% +0.023 to +0.117, p 0.004; 9 better, 0 worse, n 44)
- minilm gain over no updates: +0.055 (95% +0.017 to +0.100, p 0.008; 8 better, 0 worse, n 44)
- top gain over no updates: +0.131 (95% +0.077 to +0.192, p 0.000; 18 better, 0 worse, n 44)

## Retrieval by cohort (mean over questions)

| Arm | Cohort | n | RR | all required@10 |
| --- | --- | --- | --- | --- |
| none | current | 44 | 0.524 | 0.955 |
| none | previous | 7 | 0.440 | 1.000 |
| none | both | 6 | 0.833 | 1.000 |
| none | latest_event | 2 | 0.500 | 0.500 |
| none | context | 5 | 0.600 | 1.000 |
| none | all | 64 | 0.549 | 0.953 |
| oracle | current | 44 | 0.681 | 0.955 |
| oracle | previous | 7 | 0.321 | 0.714 |
| oracle | both | 6 | 0.694 | 0.167 |
| oracle | latest_event | 2 | 0.500 | 0.500 |
| oracle | context | 5 | 0.600 | 1.000 |
| oracle | all | 64 | 0.631 | 0.844 |
| overlap | current | 44 | 0.524 | 0.955 |
| overlap | previous | 7 | 0.440 | 1.000 |
| overlap | both | 6 | 0.833 | 1.000 |
| overlap | latest_event | 2 | 0.500 | 0.500 |
| overlap | context | 5 | 0.600 | 1.000 |
| overlap | all | 64 | 0.549 | 0.953 |
| hash | current | 44 | 0.591 | 0.955 |
| hash | previous | 7 | 0.512 | 1.000 |
| hash | both | 6 | 0.917 | 0.833 |
| hash | latest_event | 2 | 0.500 | 0.500 |
| hash | context | 5 | 0.800 | 1.000 |
| hash | all | 64 | 0.626 | 0.938 |
| minilm | current | 44 | 0.579 | 0.955 |
| minilm | previous | 7 | 0.512 | 1.000 |
| minilm | both | 6 | 0.833 | 1.000 |
| minilm | latest_event | 2 | 0.500 | 0.500 |
| minilm | context | 5 | 0.700 | 1.000 |
| minilm | all | 64 | 0.603 | 0.953 |
| top | current | 44 | 0.655 | 0.955 |
| top | previous | 7 | 0.393 | 0.714 |
| top | both | 6 | 0.917 | 0.500 |
| top | latest_event | 2 | 0.500 | 0.500 |
| top | context | 5 | 0.900 | 1.000 |
| top | all | 64 | 0.665 | 0.875 |
| random | current | 44 | 0.566 | 0.955 |
| random | previous | 7 | 0.351 | 0.771 |
| random | both | 6 | 0.858 | 0.883 |
| random | latest_event | 2 | 0.500 | 0.500 |
| random | context | 5 | 0.690 | 1.000 |
| random | all | 64 | 0.578 | 0.917 |

## Threshold sweep (reported, not part of the verdict)

| Detector | Threshold | Current recall | Wrong target (positives) | Negatives fired | Control turns fired |
| --- | --- | --- | --- | --- | --- |
| overlap | 0.2 | 0.295 | 16 | 4 | 180 of 640 |
| overlap | 0.3 | 0.114 | 7 | 0 | 58 of 640 |
| overlap | 0.4 | 0.068 | 2 | 0 | 21 of 640 |
| overlap | 0.5 | 0.000 | 0 | 0 | 14 of 640 |
| overlap | 0.6 | 0.000 | 0 | 0 | 6 of 640 |
| hash | 0.4 | 0.386 | 33 | 13 | 530 of 640 |
| hash | 0.5 | 0.386 | 31 | 13 | 371 of 640 |
| hash | 0.6 | 0.250 | 19 | 5 | 155 of 640 |
| hash | 0.7 | 0.091 | 7 | 0 | 47 of 640 |
| hash | 0.8 | 0.000 | 1 | 0 | 10 of 640 |
| minilm | 0.4 | 0.341 | 29 | 13 | 401 of 640 |
| minilm | 0.5 | 0.273 | 27 | 8 | 331 of 640 |
| minilm | 0.6 | 0.205 | 18 | 7 | 236 of 640 |
| minilm | 0.7 | 0.136 | 11 | 2 | 139 of 640 |
| minilm | 0.8 | 0.091 | 3 | 1 | 45 of 640 |

Limits: the annotations are provisional; candidates come from BM25 over the whole store filtered to earlier turns; only the decision for the new turn is applied, so control-turn fires are counted but their harm is not measured; a control-turn fire may be a genuine unlabelled update, so that rate is an upper bound; baselines are simple by design and a model-based detector is not tested here.
