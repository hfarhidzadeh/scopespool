# Private retention scale benchmark

Embedder: none (lexical search only). Sizes: 256 memories / 2 readers, 1,024 memories / 4 readers, 4,096 memories / 8 readers; 4 paired repetitions each.

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
| 256 / 2 | 3.20, 3.63 / 4.26, 5.06 | 6.15, 18.94 / 6.90, 20.85 | 249.40 / 214.82 | 22.80, 14.18 / 21.35, 10.52 | 1.00 / 4.39 | 0.94 / 3.13 |
| 1,024 / 4 | 8.23, 8.71 / 9.38, 10.22 | 97.32, 136.87 / 104.45, 150.73 | 49.40 / 45.82 | 373.94, 41.19 / 353.51, 38.42 | 1.02 / 4.67 | 1.53 / 3.99 |
| 4,096 / 8 | 30.03, 43.84 / 30.32, 39.36 | 951.51, 1655.37 / 1007.21, 1676.29 | 9.08 / 8.06 | 5511.65, 173.01 / 5646.22, 165.87 | 1.60 / 6.76 | 3.96 / 8.05 |

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
| 256 | 1, silent | 1.463 | 1.287 | 0.797 | 94,792 / 889,952 | 40,960 / 153 | 267.7 | 219 / 219 | 131 / 0 | serial p95, mixed throughput |
| 256 | 2, private | 1.572 | 1.155 | 0.850 | 94,792 / 918,792 | 40,960 / 156 | 262.6 | 219 / 219 | 123 / 0 | serial p95 |
| 256 | 3, silent | 1.182 | 0.869 | 0.908 | 94,792 / 889,952 | 40,960 / 153 | 267.7 | 219 / 219 | 129 / 0 | None |
| 256 | 4, private | 1.256 | 1.291 | 0.905 | 94,792 / 914,672 | 40,960 / 156 | 262.6 | 219 / 219 | 135 / 0 | None |
| 1,024 | 1, silent | 1.232 | 1.164 | 0.895 | 337,872 / 1,697,472 | 61,440 / 257 | 239.1 | 877 / 877 | 178 / 0 | None |
| 1,024 | 2, private | 1.456 | 1.313 | 0.691 | 337,872 / 1,726,312 | 65,536 / 260 | 252.1 | 877 / 877 | 176 / 0 | serial p95, mixed throughput |
| 1,024 | 3, silent | 1.091 | 0.992 | 1.166 | 337,872 / 1,722,192 | 61,440 / 257 | 239.1 | 877 / 877 | 179 / 0 | None |
| 1,024 | 4, private | 1.101 | 1.045 | 0.961 | 337,872 / 1,738,672 | 61,440 / 256 | 240.0 | 877 / 877 | 176 / 0 | None |
| 4,096 | 1, silent | 0.958 | 1.065 | 0.683 | 1,289,592 / 4,049,992 | 110,592 / 447 | 247.4 | 3,510 / 3,510 | 285 / 0 | mixed throughput |
| 4,096 | 2, private | 0.775 | 1.031 | 1.117 | 1,289,592 / 4,045,872 | 110,592 / 447 | 247.4 | 3,510 / 3,510 | 276 / 0 | None |
| 4,096 | 3, silent | 1.389 | 0.968 | 1.105 | 1,289,592 / 4,033,512 | 110,592 / 447 | 247.4 | 3,510 / 3,510 | 281 / 0 | serial p95 |
| 4,096 | 4, private | 0.768 | 0.993 | 0.926 | 1,289,592 / 4,045,872 | 110,592 / 450 | 245.8 | 3,510 / 3,510 | 279 / 0 | None |

5/12 repetitions missed at least one provisional flag. The JSON report preserves each arm's measurements and individual checks.

Python 3.9.6, SQLite 3.39.5, macOS-13.7.8-x86_64-i386-64bit. Schema 8, store source SHA-256 `40258276b32c693787e7addfd3b0226f9bcec53b3ae87dcacc80333467d7c337`. Elapsed time 119.4 s.

The fixture is synthetic and measures one host and runtime. Mixed throughput includes starting workers and waiting for the prune previews. WAL bytes are file sizes before the explicit checkpoint, and checkpointed DB growth includes index and page allocation. Expiry cleanup deletes rows while SQLite retains allocated pages for reuse.

Re-run with `python3 -I experiments/private_retention_scale.py --output /tmp/private_retention_scale`.
