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

The [post-split experiment](../experiments/results/private_retention_verification_post_split.md)
repeats the [original verification](../experiments/results/private_retention_verification.md)
on revision `8140298`, after both private and shared reads moved counting into a
separate transaction. All six checks passed on each of 500 seeds. On the
256-memory measurement fixture, both arms pruned the same 219 memories.
The tracking reader retained 34 entries and the silent reader retained zero.
After expiry both lists were empty, and cleanup removed all 160 private rows.

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
flag.

Three more runs on the version that also splits shared counted reads (commit
bad83c8) all passed the gate in 12 of 12 pairs:
[Python 3.9 / SQLite 3.39](../experiments/results/private_retention_scale_py39.md),
[the same with the n-gram embedder](../experiments/results/private_retention_scale_ngram_py39.md)
and [Python 3.14 / SQLite 3.53](../experiments/results/private_retention_scale_py314.md).
No run had a lock error. Private tracking costs some throughput: at 1,024 and
4,096 memories it was 7–26% lower than silent on Python 3.14 and 0–32% lower
on 3.9, and at 256 memories it adds about 3 ms per search (p95 6.2 against
9.5 ms on 3.14), consistent with the extra write transaction. Missed
provisional flags (4, 0 and 5 of 12) fall on both sides of a ratio of 1,
including pairs where silent ran first, so they look mostly like noise; the
machine's load average was about 4 to 16 with an editor open. Hybrid ranking
is about 3.5 times slower serially (p95 319 against 96 ms at 4,096), and
Python 3.14 is a little faster serially but no better under concurrency, both
in line with per-search Python work over every visible memory being the main
cost. The performance flags are provisional.

Search ranks from a few columns per visible memory and builds full memories
only for the results, and prune scores from a few columns and builds full
memories only for its candidates. An equivalence test
(`tests/test_lean_scan.py`) compares rankings, scores, links, prune previews
and applied prunes with the earlier implementation across randomized stores;
it compares against commit 8140298 and skips where that commit is absent, as
in CI's shallow checkout. Alternating the two versions in one sitting at
4,096 memories with eight readers, serial search took 83–105 ms against
238–360 ms (median), concurrent p95 fell from 7.4–9.5 s to 4.0–4.6 s, and
concurrent throughput rose from 1.7–2.0 to 3.3–3.7 searches/s. The machine was
loaded, so only the ratios are meaningful. Prune preview alone was unchanged
(256 against 253 ms with 3,385 candidates); most of its cost is building the
candidates themselves.

The [authenticated socket benchmark](../experiments/results/private_retention_socket.md)
runs the scale benchmark's three sizes through a separate CLI server process
with signed tokens, with two prune previews alongside the concurrent calls.
Its gate was fixed in the script's docstring on 2026-11-26: every request
completes; silent and private arms return identical searches, observer probes,
previews and applied prune; each private reader's list equals its own archived
results and silent lists are empty; and no other member gains a list or a
private row. The first recorded run under that gate
([run 2](../experiments/results/private_retention_socket_run2_superseded/private_retention_socket.md))
failed: 3 of 1,512 requests, silent and private, were refused with
`ConnectionRefusedError` at 4,096 memories and eight readers. The client opens
a connection per call, and socketserver's default listen queue of 5
overflowed while request threads held the GIL. The server now uses
`socket.SOMAXCONN`, and `tests/test_auth_server.py` checks that 32
connections wait in the queue (it fails with the old size). Run 3, on the
same store with only that change, passed all four criteria in 12 of 12 pairs
(1,512 of 1,512 requests). At 4,096 memories and eight readers, concurrent
throughput was 7.4–10.3 calls/s and p95 1.4–1.7 s in both arms. A fault that
records private access for the wrong member failed the attribution criteria in
2 of 2 pairs ([fault report](../experiments/results/private_retention_socket_fault.md)).
An earlier socket run at two sizes without a fixed gate is kept in
`experiments/results/private_retention_socket_run1_superseded/`.
