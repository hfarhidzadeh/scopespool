# Retraction on real text

Real LongMemEval text; no LLM. 200 trials (seeds 0 to 199); 50 hybrid, 100 linked.
Store under test: schema version 7.
See the docstring of `experiments/longmemeval_retraction.py` for the design and rule.

| Rule | Check | Held in | Needed | Holds |
| --- | --- | --- | --- | --- |
| 1 | Determinism: the same seed gives the same result | 200 of 200 (100.0%) | every trial | True |
| 2 | Probe: before retraction the scan finds every distinctive shingle (and a backup copy the text) | 200 of 200 (100.0%) | every trial | True |
| 3 | Specificity: only memories derived from retracted messages change | 200 of 200 (100.0%) | every trial | True |
| 4 | Erasure: no distinctive shingle of a retracted message in any stored value | 200 of 200 (100.0%) | every trial | True |
| 5 | Reads: no retracted text readable; unlinked reads rank like a store that never got the message | 200 of 200 (100.0%) | every trial | True |
| 6 | Rebuild: rebuildable memories rebuilt from exactly their remaining sources | 200 of 200 (100.0%) | every trial | True |
| 7 | Backup: with a key file, an earlier copy yields no retracted text | 200 of 200 (100.0%) | every trial | True |

**Verdict: retraction erases on real text**

Reported, not part of the verdict:

- Messages sampled 20000; retractable (3 or more distinctive shingles): 18993 of 20000 (95.0%).
- Memories derived from a retracted message: 396; of those, with a remaining source to rebuild from: 178 (in 131 trials).
- Reads against the never-written reference, per query. Unlinked trials: identical 898, same ranking with other scores 0, different 0. Linked trials (not in the verdict): identical 690, same ranking 47, different 163.
- Trials in which the raw database file still holds the first 40 characters of a retracted message that no other message shares: 0 of 200 (0.0%).
- Undeclared copies (memories repeating a retracted message without listing it as a source): 398 written, 398 still readable. The store cannot find them; this is a known limit.

Limits: real text, but the derived memories are extractive joins, not model summaries, and the two-member channel is invented. A model-based consolidator, near-duplicate text, paraphrased copies and the `record_access` side channel are not tested. Distinctive shingles define 'its words'; a paraphrase of a retracted message would not be found.
