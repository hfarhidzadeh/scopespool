# Retraction on real text

Real LongMemEval text; no LLM. 40 trials (seeds 0 to 39); 10 hybrid, 20 linked.
Store under test: schema version 7; injected fault: no-rebuild.
See the docstring of `experiments/longmemeval_retraction.py` for the design and rule.

| Rule | Check | Held in | Needed | Holds |
| --- | --- | --- | --- | --- |
| 1 | Determinism: the same seed gives the same result | 40 of 40 (100.0%) | every trial | True |
| 2 | Probe: before retraction the scan finds every distinctive shingle (and a backup copy the text) | 40 of 40 (100.0%) | every trial | True |
| 3 | Specificity: only memories derived from retracted messages change | 40 of 40 (100.0%) | every trial | True |
| 4 | Erasure: no distinctive shingle of a retracted message in any stored value | 40 of 40 (100.0%) | every trial | True |
| 5 | Reads: no retracted text readable; reads rank like a store that never got the message | 18 of 40 (45.0%) | every trial | False |
| 6 | Rebuild: rebuildable memories rebuilt from exactly their remaining sources | 0 of 40 (0.0%) | every trial | False |
| 7 | Backup: with a key file, an earlier copy yields no retracted text | 40 of 40 (100.0%) | every trial | True |

**Verdict: retraction does not erase (rules 5, 6 failed, first failing seed 0)**

Reported, not part of the verdict:

- Messages sampled 4000; retractable (3 or more distinctive shingles): 3814 of 4000 (95.3%).
- Memories derived from a retracted message: 80; of those, with a remaining source to rebuild from: 31 (in 22 trials).
- Reads against the never-written reference, per query. Unlinked trials: identical 79, same ranking with other scores 41, different 63. Linked trials (also included in the reads verdict): identical 78, same ranking 51, different 49.
- Trials in which the raw database file still holds the first 40 characters of a retracted message that no other message shares: 0 of 40 (0.0%).
- Undeclared copies (memories repeating a retracted message without listing it as a source): 81 written, 81 still readable. The store cannot find them; this is a known limit.

Limits: real text, but the derived memories are extractive joins, not model summaries, and the two-member channel is invented. A model-based consolidator, near-duplicate text, paraphrased copies and the `record_access` side channel are not tested. Distinctive shingles define 'its words'; a paraphrase of a retracted message would not be found.

Validation: rule 5 failed in 22 of 22 trials in scope (100.0%): detected.
