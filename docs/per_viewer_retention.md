# Private retention for named viewers

The first increment gives a named reader a personal list of recently used memories after ordinary shared pruning. It uses the original memory rows and applies the reader's current channel and source visibility. Shared search, history, claims, and pruning continue to use the shared lifecycle.

```python
reader = store.for_viewers("alice")  # the trusted caller supplies the identity
reader.search("launch checklist", record_private_access=True)
# Later, after an administrator runs shared pruning:
for item in reader.list_retained_memories():
    print(item.memory.content)
```

## Reader and audience

- The trusted local Python caller binds a reader with `store.for_viewers(member_id)` and uses `reader.search(query, record_private_access=True)` to track returned memories for that member. The option requires a single named viewer. A group audience and an administrative search without viewers have no private tracking actor.
- Omit `record_access` when using `record_private_access=True`. An explicit `record_access=True` chooses shared tracking. An explicit `record_access=False`, or a named read with both options omitted, leaves the retention state alone.
- The tracked search returns the ordinary search results. An authorized singleton reader calls `reader.list_retained_memories()` to retrieve their personal list. Each item holds the archived memory and the reader's private count and timestamp. Standard search results, `get_memory`, `history`, and shared lists do not include those counts or timestamps.
- The Unix socket server exposes private retention only for the token's member: `search` takes a boolean `record_private_access`, and `list_retained_memories` takes only `limit`. Both refuse any audience (even one made of the caller's own token) and any `member_id` or `viewers` argument, because choosing an actor from a requested audience or accepting an arbitrary actor ID from a client would allow activity attribution to the wrong member. `ScopeSpoolClient.list_retained_memories()` is the client call.
- The CLI offers `search --private` and `retained`, each with exactly one member in `--viewers`. The CLI is a trusted local caller: whoever runs it can name any viewer, so it is not an authentication boundary; the server is.

## Lifecycle and migration

- A private counter is keyed by member and memory ID, with one row per pair. A tracked search ranks in a read transaction, so it never holds SQLite's write lock while ranking. It then increments the returned rows in a separate short write transaction, which first checks each row again: the reader must still be a current member of its channel, its sources must still be visible and not retracted, and it must not be stale or archived other than by pruning. A row pruned between the two transactions is still counted, the same outcome as if the read had finished first. A row superseded in between is counted too; the claim view hides it from the personal list. Shared counted reads (`record_access=True`, and the default for reads without viewers) use the same split, but a memory pruned in between gains no shared count, so the prune wins that race; this was accepted because applied prunes are rare administrative actions (`tests/test_shared_access_transactions.py`). A 90-day window from the last private access bounds how long a counter can qualify a memory for the personal list. Listing the collection does not renew it.
- Ordinary administrative pruning marks an archive as a prune. Its decision still uses the existing shared activity and policy. A private list includes a pruned row only while its counter is fresh and the row is currently visible and has not been superseded in this viewer's claim view. It does not restore or re-rank that row in shared search.
- A member leaving a channel clears their counters for memories in that channel and memories sourced from it. Rejoining starts a new interval of private use. Retraction deletes counters for invalidated derivations in the same transaction as clearing their text. A rebuild has its own ID and starts without inherited activity. Administrative restore clears the prune mark so the row leaves the personal list while active. Physical memory deletion would cascade to the counter row.
- A schema upgrade from version 7 creates an empty counter table and a nullable prune marker. Historic shared counters remain attributed to the shared memory, and pre-upgrade archives lack the new prune marker. The upgrade leaves existing text, vectors, keys, and links in place.
- A real prune can drop expired private counter rows. All retention comparisons use UTC timestamps, and a simulated prune date is used only for shared decisions. The personal list does not copy contents, embeddings, or query text. An optional keyed backup still has the existing content-key behavior. Database backups contain private counter metadata, so protect them with the same trust boundary as the database file. A member-facing guarantee covers returned results under store authorization and excludes file-owner inspection and resource timing.

## Verification

Use a fixture with a query-visible memory eligible for shared pruning and compare two runs that differ only in one member's decision to track their access. Shared previews and outcomes must match. After pruning, only the tracking member should have a personal entry with their own metadata. The untracked member, a disjoint member, and a shared group must have the same results and metadata in both runs.

`tests/test_per_viewer_retention.py` includes the paired comparison over 500 seeds. It compares observer search results, history and lists, their personal lists, and shared prune previews and outcomes. It also checks expiration, leave and rejoin, source-channel departure, retraction, restore, migration, and concurrent increments.

The [recorded private retention experiment](../experiments/results/private_retention_verification.md)
compares no read, the named default, explicit silence, and private tracking.
All five checks and the personal retention benefit held across 500 paired
trials. It also records SQLite timings and storage growth on a 256-memory
fixture. That report was recorded before ranking and recording were split
into two transactions; the regression tests above, including the 500-seed
paired comparison, pass on the split version.

`tests/test_private_retention_races.py` runs events between ranking and
recording: the reader leaving the memory's channel or its source channel, a
source retracted, a prune, an archive that is not a prune, and a supersession.
It also checks that another connection can take the write lock while ranking
runs; before the split that check failed with "database is locked".

The [scale benchmark](../experiments/results/private_retention_scale.md)
(256, 1,024 and 4,096 memories with 2, 4 and 8 readers, four paired
repetitions each) has an acceptance gate fixed in the script before the rerun:
no lock timeouts or lock errors, matching shared and observer results between
silent and private arms, and a retained result for every eligible reader. The
gate passed in 12 of 12 pairs. The pilot, run before the split, had two lock
timeouts in 288 private mixed searches at 4,096 memories and eight readers
([pilot report](../experiments/results/private_retention_scale_run1_superseded/private_retention_scale.md)).
After the split, private and silent mixed p95 latencies were within 6% of each
other at 4,096 memories, but both arms took about 5.6 s at p95 under eight
concurrent readers, and one of 12 repetitions missed a provisional performance
flag. Server integration needs its own verification, and the provisional flags
are not yet release budgets.
