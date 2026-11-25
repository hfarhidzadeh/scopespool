# LongMemEval evidence audit — 2026-11-25

**Status: AI-authored review; nine proposed category decisions accepted by the
project owner on 2026-11-25.** This review
checks the 75-row [label sheet](sheet.csv), which covers 70 unique questions and
five repeated rows. It cross-checks disputed cases against full source sessions
in `data/longmemeval/longmemeval_s_cleaned.json`. The acceptance is recorded in
the separate [category-approved annotation snapshot](../../../eval/longmemeval_knowledge_update_annotations_v3_category_approved_2026-11-25.json).
It is not a blind human reannotation of all 70 questions, and the evidence
groups and update relations remain partly AI-derived and provisional.

The deliverables are the [filled review sheet](sheet_labeled_ai_audited_2026-11-25.csv)
and a separate [v3 annotation revision](../../../eval/longmemeval_knowledge_update_annotations_v3_ai_audited_2026-11-25.json).
The original sheet, labels, and the annotation snapshot used for the recorded
v3 results are unchanged.

## Checks and cohort

- All 75 rows have a valid category. The five repeated pairs agree in all five
  cases, exceeding the sheet's 4-of-5 consistency threshold.
- Across 70 unique questions, this AI audit agrees with 61 original categories
  and 64 categories in the earlier AI review. These are *agreement* figures, not
  accuracy against an independent gold standard. The scoring script labels its
  output “researcher categories” generically; the decisions in this sheet are
  AI-authored.
- The proposed cohort has 44 `current`, 7 `previous`, 6 `both`, 2
  `latest_event`, 5 `context`, and 6 `exclude` questions. The v3 converter
  validated 64 included sets and six excluded annotations.

## Category decisions accepted by the project owner

| Question ID | Original → proposed | Evidence issue |
| --- | --- | --- |
| `2133c1b5` | current → exclude | The answer-bearing session is later than the question on the same date. |
| `5c40ec5b` | current → context | The older Alex turn gives a first meeting, without an exact earlier meetup count. |
| `cf22b7bf` | current → context | Five pounds in one month and ten pounds since starting the gym measure different intervals. |
| `26bdc477` | current → context | The earlier camera turn lists three example trips but gives no exact earlier total. |
| `42ec0761` | current → context | Misplacing the usual screwdriver does not establish prior lack of a spare; the spare was picked up “a while back.” |
| `50635ada` | previous → exclude | The user reports becoming *eligible* for Premier Silver, not holding that status. The benchmark answer is unsupported. |
| `07741c45` | current → exclude | The shoe-rack evidence describes a plan. A later user turn in the same session still looks forward to storing the sneakers there. |
| `9ea5eabc` | latest_event → exclude | Paris was “last month”; Hawaii was “recent” without a trip date. Report order does not establish which trip was latest. |
| `0977f2af` | previous → exclude | The Air Fryer was bought the day before its May 21 report; the “new” Instant Pot has no purchase date. Purchase order is unproven. |

The proposed annotation revision removes the supersession edge for companion
question `07741c44` while retaining its directly supported earlier answer:
the sneakers were under the bed. A planned shoe-rack move is not a confirmed
replacement. The coffee question `c6853660` continues to use the later
unmarked user confirmation as its update point. The existing caveats for
approximate answers, wording, and chronology remain in the revision.

## Use of this review

The filled CSV can be scored with:

```text
PYTHONPATH=src python3 experiments/label_review_sheet.py --score experiments/results/label_review/sheet_labeled_ai_audited_2026-11-25.csv
```

The nine category decisions above were accepted by the project owner on
2026-11-25. The remaining evidence flags in the CSV, required-evidence groups,
and supersession relations still need independent review before calling the
whole annotation set adjudicated. The [category-approved v3 run](../longmemeval_v3_category_approved_2026-11-25.md)
and [corrected detector baseline](../longmemeval_detector_baselines_category_approved_2026-11-25.md)
use that snapshot and passed their controls. Their results remain provisional
because the evidence and update relations have not all been independently
adjudicated. Recorded earlier metrics still describe their own annotation
snapshots.
