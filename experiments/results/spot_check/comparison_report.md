# Spot-check label comparison

Updated 2026-11-24. The original `sheet.csv` is unchanged.

`sheet_labeled_checked.csv` preserves the reviewed labels and adds `arm`, `workspace`, and `key_owner` from `key.json` for auditability.

The key does not contain a gold `label` field, so it cannot provide ordinary per-row label accuracy. It does provide the experiment arm, which gives this consistency check:

| Arm | Rows | Reviewed labels | Strict expected mode | Strict agreement |
|---|---:|---|---|---:|
| control | 20 | 18 owner, 1 other (R21), 1 unsure (R23) | owner | 18/20 (90.0%) |
| built | 40 | 34 other, 5 unsure (R11, R27, R30, R34, R59), 1 owner (R55) | other | 34/40 (85.0%) |
| all | 60 | 52 strict-mode matches | arm mode | 52/60 (86.7%) |

The six built exceptions were traced against their workspace plans in `outcome.md`; none was a leak. The control exceptions are annotation discrepancies, not key-confirmed leaks. Treat the 86.7% figure as arm consistency, not gold-label accuracy.

## Outputs

- `sheet_labeled_checked.csv`: reviewed spot-check labels plus key metadata.
- `../label_review/sheet_labeled.csv`: all 75 label-review rows plus key-backed `repeat` (`true` for 5, `false` for 70).
