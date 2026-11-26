# Private retention verification

**Verification passed.** Schema 8. 500 seeds compare no read, named default, explicit silence, and private tracking. Each seed varies the topic, fixture order, age, and actor search limit. The private arm is repeated for determinism.

The actor is Alice, with a private channel and a shared channel. The observers are Bob in her shared channel, Alice and Bob as a joint audience, and Carol in a disjoint channel. The exact comparison includes rankings, scores, links, shared access fields, direct reads, history, active and archived lists, the observers' personal lists where available, and shared prune previews and outcomes.

| Check | Passed | Required |
| --- | ---: | ---: |
| Repeated private arm matches exactly | 500/500 | 500/500 |
| Default and explicit silence match no read | 500/500 | 500/500 |
| Exact rankings match across paired reads and after pruning | 500/500 | 500/500 |
| Disjoint observer outputs are invariant | 500/500 | 500/500 |
| Shared metadata and prune previews and outcomes match | 500/500 | 500/500 |
| Tracking reader retains exactly the eligible read results | 500/500 | 500/500 |

## Local SQLite measurements

Each arm uses a separate temporary WAL database on the same machine with 256 synthetic memories, 8 topics, four named members, and a search limit of 5. Silent runs first. Timing includes each API call's transaction and SQLite connection. Concurrent throughput includes starting four workers. Applied pruning is timed once per arm.

| Measure | Silent | Private |
| --- | ---: | ---: |
| Serial search p50 / p95 | 6.628 / 7.300 ms | 7.889 / 12.413 ms |
| Concurrent search p50 / p95 | 34.577 / 122.559 ms | 74.684 / 101.835 ms |
| Personal list p50 / p95 | 0.877 / 1.657 ms | 1.946 / 2.528 ms |
| Prune preview p50 / p95 | 6.053 / 9.301 ms | 5.715 / 6.656 ms |
| Concurrent search calls/s | 78.057 | 57.984 |
| Applied prune, ms | 18.706 | 12.353 |
| Expiry cleanup, ms | 1.471 | 2.215 |
| Shared memories archived | 219 | 219 |
| Personal results before expiry | 0 | 34 |
| Personal results after expiry | 0 | 0 |

## Storage

| Stage | Silent DB / WAL bytes / rows | Private DB / WAL bytes / rows |
| --- | ---: | ---: |
| initial | 196608 / 0 / 0 | 196608 / 0 / 0 |
| after serial | 196608 / 0 / 0 | 196608 / 791072 / 40 |
| after concurrent | 196608 / 0 / 0 | 196608 / 1849912 / 160 |
| checkpointed | 196608 / 0 / 0 | 241664 / 0 / 160 |
| before cleanup | 196608 / 90672 / 0 | 241664 / 90672 / 160 |
| after cleanup | 196608 / 90672 / 0 | 241664 / 156592 / 0 |

Python 3.9.6, SQLite 3.39.5, macOS-13.7.8-x86_64-i386-64bit. Store source SHA-256 `55bfa04a5e441c1b53d1bc6c53986e627ee49e16658dc50b4e93dba4c3faa99b`.

The local timings describe one small corpus and one machine. The private personal list contains entries and the silent list is empty. WAL measurements reflect write volume between the checkpoint boundaries. Expiry removes rows without compacting the database. This fixture verifies visible API results. Server integration, observation of timing, large workloads, and release performance budgets remain separate work.

Reproduce into temporary report files with `python -I experiments/private_retention_verification.py --output /tmp/private_retention_verification`.
