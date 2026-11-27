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
| 256 / 2 | 3.45, 5.39 / 5.08, 6.38 | 7.94, 20.65 / 10.06, 25.83 | 217.18 / 173.94 | 12.38, 7.18 / 11.33, 7.75 | 1.20 / 4.36 | 0.95 / 2.51 |
| 1,024 / 4 | 8.60, 11.57 / 10.47, 13.07 | 75.69, 133.40 / 51.39, 138.84 | 58.94 / 63.84 | 29.43, 21.32 / 32.05, 19.14 | 1.12 / 3.93 | 1.23 / 3.01 |
| 4,096 / 8 | 31.91, 35.98 / 34.56, 38.71 | 537.29, 1277.10 / 569.57, 1288.62 | 12.92 / 12.52 | 95.68, 87.96 / 92.53, 91.78 | 1.12 / 5.40 | 2.69 / 6.33 |

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
| 256 | 1, silent | 1.269 | 1.272 | 0.813 | 94,792 / 889,952 | 40,960 / 153 | 267.7 | 219 / 219 | 131 / 0 | None |
| 256 | 2, private | 0.864 | 1.637 | 0.696 | 94,792 / 922,912 | 40,960 / 156 | 262.6 | 219 / 219 | 123 / 0 | mixed p95, mixed throughput |
| 256 | 3, silent | 1.513 | 0.973 | 0.900 | 94,792 / 894,072 | 40,960 / 153 | 267.7 | 219 / 219 | 129 / 0 | serial p95 |
| 256 | 4, private | 1.099 | 1.231 | 0.789 | 94,792 / 918,792 | 40,960 / 156 | 262.6 | 219 / 219 | 135 / 0 | mixed throughput |
| 1,024 | 1, silent | 0.932 | 1.039 | 1.068 | 337,872 / 1,701,592 | 61,440 / 257 | 239.1 | 877 / 877 | 178 / 0 | None |
| 1,024 | 2, private | 1.349 | 0.999 | 0.987 | 337,872 / 1,738,672 | 65,536 / 260 | 252.1 | 877 / 877 | 176 / 0 | serial p95 |
| 1,024 | 3, silent | 1.230 | 1.142 | 1.129 | 337,872 / 1,730,432 | 61,440 / 257 | 239.1 | 877 / 877 | 179 / 0 | None |
| 1,024 | 4, private | 1.088 | 1.001 | 1.139 | 337,872 / 1,709,832 | 61,440 / 256 | 240.0 | 877 / 877 | 176 / 0 | None |
| 4,096 | 1, silent | 1.148 | 0.978 | 1.033 | 1,289,592 / 4,066,472 | 110,592 / 447 | 247.4 | 3,510 / 3,510 | 285 / 0 | None |
| 4,096 | 2, private | 0.924 | 0.891 | 0.934 | 1,289,592 / 4,054,112 | 110,592 / 447 | 247.4 | 3,510 / 3,510 | 276 / 0 | None |
| 4,096 | 3, silent | 1.116 | 1.005 | 0.973 | 1,289,592 / 4,037,632 | 110,592 / 447 | 247.4 | 3,510 / 3,510 | 281 / 0 | None |
| 4,096 | 4, private | 1.077 | 1.029 | 1.052 | 1,289,592 / 4,041,752 | 110,592 / 450 | 245.8 | 3,510 / 3,510 | 279 / 0 | None |

4/12 repetitions missed at least one provisional flag. The JSON report preserves each arm's measurements and individual checks.

Python 3.14.8, SQLite 3.53.4, macOS-13.7.8-x86_64-i386-64bit-Mach-O. Schema 8, store source SHA-256 `7f4276340281b9389ccc61e58afa0c0ca93d75a7e08f464597066543d507c926`. Elapsed time 94.0 s.

The fixture is synthetic and measures one host and runtime. Mixed throughput includes starting workers and waiting for the prune previews. WAL bytes are file sizes before the explicit checkpoint, and checkpointed DB growth includes index and page allocation. Expiry cleanup deletes rows while SQLite retains allocated pages for reuse.

Re-run with `python3 -I experiments/private_retention_scale.py --output /tmp/private_retention_scale`.
