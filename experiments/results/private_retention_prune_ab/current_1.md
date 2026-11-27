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
| 256 / 2 | 4.11, 5.50 / 5.06, 7.50 | 6.78, 16.62 / 8.31, 21.16 | 251.36 / 207.52 | 9.84, 9.78 / 11.30, 9.77 | 1.38 / 5.75 | 1.48 / 6.34 |
| 1,024 / 4 | 9.34, 15.18 / 10.34, 15.77 | 70.96, 127.59 / 68.73, 138.94 | 58.88 / 58.26 | 25.84, 33.60 / 27.82, 25.48 | 1.34 / 5.92 | 1.83 / 3.85 |
| 4,096 / 8 | 38.55, 48.53 / 41.71, 51.81 | 530.24, 1071.51 / 516.82, 1101.19 | 13.74 / 14.25 | 122.88, 103.97 / 122.01, 110.21 | 1.27 / 8.71 | 3.63 / 11.92 |

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
| 256 | 1, silent | 1.572 | 1.930 | 0.713 | 94,792 / 894,072 | 40,960 / 153 | 267.7 | 219 / 219 | 131 / 0 | serial p95, mixed p95, mixed throughput |
| 256 | 2, private | 1.125 | 1.037 | 0.810 | 94,792 / 922,912 | 40,960 / 156 | 262.6 | 219 / 219 | 123 / 0 | cleanup |
| 256 | 3, silent | 1.260 | 1.065 | 0.948 | 94,792 / 894,072 | 40,960 / 153 | 267.7 | 219 / 219 | 129 / 0 | None |
| 256 | 4, private | 1.443 | 1.064 | 0.835 | 94,792 / 914,672 | 40,960 / 156 | 262.6 | 219 / 219 | 135 / 0 | serial p95 |
| 1,024 | 1, silent | 1.102 | 0.954 | 1.034 | 337,872 / 1,701,592 | 61,440 / 257 | 239.1 | 877 / 877 | 178 / 0 | None |
| 1,024 | 2, private | 1.076 | 1.450 | 0.928 | 337,872 / 1,742,792 | 65,536 / 260 | 252.1 | 877 / 877 | 176 / 0 | mixed p95 |
| 1,024 | 3, silent | 1.125 | 0.950 | 1.000 | 337,872 / 1,738,672 | 61,440 / 257 | 239.1 | 877 / 877 | 179 / 0 | None |
| 1,024 | 4, private | 1.001 | 1.053 | 0.979 | 337,872 / 1,726,312 | 61,440 / 256 | 240.0 | 877 / 877 | 176 / 0 | None |
| 4,096 | 1, silent | 1.274 | 0.990 | 1.017 | 1,289,592 / 4,066,472 | 106,496 / 447 | 238.2 | 3,510 / 3,510 | 285 / 0 | None |
| 4,096 | 2, private | 0.828 | 0.988 | 1.055 | 1,289,592 / 4,049,992 | 110,592 / 447 | 247.4 | 3,510 / 3,510 | 276 / 0 | None |
| 4,096 | 3, silent | 1.259 | 1.132 | 0.897 | 1,289,592 / 4,095,312 | 110,592 / 447 | 247.4 | 3,510 / 3,510 | 281 / 0 | None |
| 4,096 | 4, private | 0.783 | 1.080 | 1.106 | 1,289,592 / 4,045,872 | 110,592 / 450 | 245.8 | 3,510 / 3,510 | 279 / 0 | cleanup |

5/12 repetitions missed at least one provisional flag. The JSON report preserves each arm's measurements and individual checks.

Python 3.9.6, SQLite 3.39.5, macOS-13.7.8-x86_64-i386-64bit. Schema 8, store source SHA-256 `7f4276340281b9389ccc61e58afa0c0ca93d75a7e08f464597066543d507c926`. Elapsed time 97.6 s.

The fixture is synthetic and measures one host and runtime. Mixed throughput includes starting workers and waiting for the prune previews. WAL bytes are file sizes before the explicit checkpoint, and checkpointed DB growth includes index and page allocation. Expiry cleanup deletes rows while SQLite retains allocated pages for reuse.

Re-run with `python3 -I experiments/private_retention_scale.py --output /tmp/private_retention_scale`.
