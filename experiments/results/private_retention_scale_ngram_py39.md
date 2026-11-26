# Private retention scale benchmark

Embedder: ngram (NGramHashEmbedder, hybrid search; each arm embeds the fixture at its first observer read, before any timed call). Sizes: 256 memories / 2 readers, 1,024 memories / 4 readers, 4,096 memories / 8 readers; 4 paired repetitions each.

**Acceptance gate: pass.** Pre-registered in the script's docstring; each criterion must hold in every pair.

| Criterion | Pairs held |
| --- | ---: |
| (a) no lock timeouts or lock errors, no unpaired attempts | 12/12 |
| (b) shared and observer results match between arms | 12/12 |
| (c) a retained result for every eligible reader | 12/12 |

**Behavior checks passed in 12/12 paired repetitions.** Silent and private arms compared exact search results, preview and applied prune results, and observer rankings for an overlapping peer, a joint audience, and a disjoint viewer. Each private arm checked the expected retained entries, private row counts, and expiry cleanup. Search and preview comparisons include matched calls that completed in both modes.

**All calls completed in 12/12 pairs.** Lock errors and failed wait times are recorded without retries.

## Fixed workload

Each size starts from a shared synthetic fixture copied into independent WAL databases. Mode order alternates across repetitions. Each pair uses the same queries in both modes. Each arm runs 4 warmup and 24 serial searches. Before and after one applied prune, each reader makes 6 and 3 concurrent searches, respectively, alongside 2 prune previews per phase. The personal list receives 12 timed reads. Cleanup runs with the private access clock advanced 91 days.

The local provisional flags allow private/silent p95 ratios up to 1.30 in serial and 1.35 in the mixed phase, throughput at least 0.80 of silent, at most 1,024 added checkpointed bytes per private row, and at most 50 ms for private cleanup. These flags identify workloads to investigate before planning a release.

## Results by workload

Values are medians across repetitions. Each cell lists silent / private values. Search and preview p50/p95 cover successful calls. Throughput counts successful searches over all elapsed time, including time spent waiting on failed calls.

| Memories / readers | Serial p50 / p95 (ms) | Mixed p50 / p95 (ms) | Successful mixed searches/s | Prune preview p95 / apply (ms) | Personal list p95 (ms) | Cleanup (ms) |
| --- | --- | --- | ---: | --- | ---: | ---: |
| 256 / 2 | 21.64, 22.93 / 22.48, 24.99 | 44.50, 85.19 / 43.84, 76.43 | 51.28 / 54.18 | 38.49, 10.35 / 39.17, 9.71 | 1.13 / 4.26 | 1.40 / 3.86 |
| 1,024 / 4 | 78.67, 87.32 / 79.65, 87.26 | 511.87, 701.33 / 510.65, 687.25 | 9.67 / 9.48 | 613.37, 43.53 / 580.94, 37.02 | 1.56 / 4.89 | 3.50 / 5.87 |
| 4,096 / 8 | 302.94, 318.71 / 303.65, 320.09 | 5545.69, 7360.59 / 5445.85, 7242.43 | 1.76 / 1.82 | 6369.38, 143.14 / 5650.51, 160.83 | 1.73 / 6.16 | 11.52 / 15.10 |

## Availability

| Memories | Pair | Mixed searches completed, silent / private | Private mixed lock wait p95 (ms) | Unpaired search or preview attempts |
| ---: | ---: | ---: | ---: | ---: |
| 256 | 1 | 18/18 / 18/18 | n/a | 0 |
| 256 | 2 | 18/18 / 18/18 | n/a | 0 |
| 256 | 3 | 18/18 / 18/18 | n/a | 0 |
| 256 | 4 | 18/18 / 18/18 | n/a | 0 |
| 1,024 | 1 | 36/36 / 36/36 | n/a | 0 |
| 1,024 | 2 | 36/36 / 36/36 | n/a | 0 |
| 1,024 | 3 | 36/36 / 36/36 | n/a | 0 |
| 1,024 | 4 | 36/36 / 36/36 | n/a | 0 |
| 4,096 | 1 | 72/72 / 72/72 | n/a | 0 |
| 4,096 | 2 | 72/72 / 72/72 | n/a | 0 |
| 4,096 | 3 | 72/72 / 72/72 | n/a | 0 |
| 4,096 | 4 | 72/72 / 72/72 | n/a | 0 |

## Paired ratios and storage

| Memories | Pair, first arm | Serial p95 ratio | Mixed p95 ratio | Throughput ratio | WAL bytes, silent / private | Added DB bytes / private rows | Added bytes/row | Archived, silent / private | Personal results before / after expiry | Flags missed |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 256 | 1, silent | 0.715 | 0.799 | 1.358 | 1,207,192 / 2,088,872 | 40,960 / 164 | 249.8 | 219 / 219 | 127 / 0 | None |
| 256 | 2, private | 1.120 | 1.062 | 0.953 | 1,207,192 / 2,084,752 | 40,960 / 170 | 240.9 | 219 / 219 | 122 / 0 | None |
| 256 | 3, silent | 1.150 | 0.954 | 0.976 | 1,207,192 / 2,080,632 | 40,960 / 165 | 248.2 | 219 / 219 | 135 / 0 | None |
| 256 | 4, private | 1.000 | 0.703 | 1.183 | 1,207,192 / 2,072,392 | 40,960 / 168 | 243.8 | 219 / 219 | 130 / 0 | None |
| 1,024 | 1, silent | 1.123 | 1.031 | 1.039 | 337,872 / 1,742,792 | 65,536 / 268 | 244.5 | 877 / 877 | 184 / 0 | None |
| 1,024 | 2, private | 0.930 | 0.820 | 0.983 | 337,872 / 1,779,872 | 65,536 / 265 | 247.3 | 877 / 877 | 180 / 0 | None |
| 1,024 | 3, silent | 0.826 | 1.111 | 1.029 | 337,872 / 1,783,992 | 65,536 / 266 | 246.4 | 877 / 877 | 186 / 0 | None |
| 1,024 | 4, private | 1.093 | 1.000 | 0.926 | 337,872 / 1,742,792 | 65,536 / 264 | 248.2 | 877 / 877 | 180 / 0 | None |
| 4,096 | 1, silent | 1.057 | 0.970 | 1.026 | 2,879,912 / 840,512 | 110,592 / 449 | 246.3 | 3,510 / 3,510 | 276 / 0 | None |
| 4,096 | 2, private | 0.910 | 0.869 | 0.989 | 2,879,912 / 873,472 | 110,592 / 446 | 248.0 | 3,510 / 3,510 | 280 / 0 | None |
| 4,096 | 3, silent | 1.060 | 0.982 | 1.036 | 2,879,912 / 832,272 | 110,592 / 448 | 246.9 | 3,510 / 3,510 | 284 / 0 | None |
| 4,096 | 4, private | 0.960 | 1.104 | 1.093 | 2,879,912 / 881,712 | 110,592 / 447 | 247.4 | 3,510 / 3,510 | 275 / 0 | None |

0/12 repetitions missed at least one provisional flag. The JSON report preserves each arm's measurements and individual checks.

Python 3.9.6, SQLite 3.39.5, macOS-13.7.8-x86_64-i386-64bit. Schema 8, store source SHA-256 `55bfa04a5e441c1b53d1bc6c53986e627ee49e16658dc50b4e93dba4c3faa99b`. Elapsed time 549.2 s.

The fixture is synthetic and measures one host and runtime. Mixed throughput includes starting workers and waiting for the prune previews. WAL bytes are file sizes before the explicit checkpoint, and checkpointed DB growth includes index and page allocation. Expiry cleanup deletes rows while SQLite retains allocated pages for reuse.

Re-run with `python3 -I experiments/private_retention_scale.py --output /tmp/private_retention_scale`.
