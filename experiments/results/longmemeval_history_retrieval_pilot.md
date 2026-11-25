# History-preserving LongMemEval retrieval pilot

This provisional lexical evaluation uses the v3 session links and oracle intent from annotation categories. Supersession edges come from the selected annotations.

Kept searches all turns. Archive applies the annotated whole-turn supersessions. Demote current moves superseded turns to the end of the full search ranking for current intent and uses the kept ranking for other intents.

| Policy | Cohort | Questions | All required@10 | RR@10 | Stale-first |
| --- | --- | ---: | ---: | ---: | ---: |
| kept | all | 64 | 0.953 | 0.549 | 0.477 (n=44) |
| kept | current intent | 44 | 0.955 | 0.524 | 0.477 (n=44) |
| kept | history intent | 13 | 1.000 | 0.622 | - |
| kept | both category | 6 | 1.000 | 0.833 | - |
| kept | older-required evidence | 7 | 1.000 | 0.690 | - |
| archive | all | 64 | 0.844 | 0.631 | 0.000 (n=44) |
| archive | current intent | 44 | 0.955 | 0.681 | 0.000 (n=44) |
| archive | history intent | 13 | 0.462 | 0.494 | - |
| archive | both category | 6 | 0.167 | 0.694 | - |
| archive | older-required evidence | 7 | 0.000 | 0.452 | - |
| demote current | all | 64 | 0.953 | 0.649 | 0.000 (n=44) |
| demote current | current intent | 44 | 0.955 | 0.670 | 0.000 (n=44) |
| demote current | history intent | 13 | 1.000 | 0.622 | - |
| demote current | both category | 6 | 1.000 | 0.833 | - |
| demote current | older-required evidence | 7 | 1.000 | 0.690 | - |

Stale-first means an outdated turn precedes the first relevant turn among answer-related top-10 hits. A stale hit with no relevant hit also counts.

## Checks

- whole turn archive removes superseded turns — pass.
- demotion keeps all candidates — pass.
- no edges leave all rankings unchanged — pass.
- demotion leaves non current rankings unchanged — pass.

Current-intent demotion changed the full ranking for 44 questions.

The pilot advances to a reviewed follow-up if the controls pass, current-intent mean RR improves, the older-required cohort is nonempty, and no current-intent or older-required case loses all-required@10. The pilot met these criteria.

The result depends on oracle supersession edges and supplied intent. Evidence groups and edges remain provisional. The study does not evaluate intent classification, automated updates, as-of retrieval, or semantic search.

## Reproduce

From the repository root, with the cleaned LongMemEval data installed, run:

```bash
python -I experiments/longmemeval_history_retrieval.py \
  --annotations eval/longmemeval_knowledge_update_annotations_v3_category_approved_2026-11-25.json \
  --oracle-intent-from-annotations
```

- Data SHA-256: `d6f21ea9d60a0d56f34a05b609c79c88a451d2ae03597821ea3d5a9678c3a442`
- Annotation file: `longmemeval_knowledge_update_annotations_v3_category_approved_2026-11-25.json`
- Annotation SHA-256: `a2b75e3795557b9aa15fe84fda8eaba2284458ba947eafc22e353698936ae2b8`
- Resolved intent map SHA-256: `a453623b058a74e7c757d45790067e1ebc09865ea6375122dd6b51b86b318bdc`
- Runtime: Python 3.9.6, SQLite 3.39.5
