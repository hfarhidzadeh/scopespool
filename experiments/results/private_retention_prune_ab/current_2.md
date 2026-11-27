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
| 256 / 2 | 4.26, 6.16 / 4.39, 6.84 | 5.98, 15.26 / 7.42, 23.98 | 277.76 / 221.53 | 8.87, 10.21 / 11.25, 6.98 | 1.54 / 5.69 | 0.94 / 2.99 |
| 1,024 / 4 | 10.22, 15.97 / 9.87, 15.73 | 75.26, 131.52 / 69.33, 121.86 | 58.72 / 61.17 | 28.17, 34.81 / 26.51, 26.53 | 1.49 / 4.78 | 1.75 / 3.73 |
| 4,096 / 8 | 43.77, 51.84 / 42.73, 53.57 | 499.37, 1015.02 / 505.60, 1050.97 | 14.57 / 15.19 | 117.43, 109.99 / 122.46, 133.92 | 1.75 / 8.03 | 5.61 / 8.65 |

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
| 256 | 1, silent | 1.388 | 1.696 | 0.759 | 94,792 / 889,952 | 40,960 / 153 | 267.7 | 219 / 219 | 131 / 0 | serial p95, mixed p95, mixed throughput |
| 256 | 2, private | 0.773 | 1.205 | 0.795 | 94,792 / 922,912 | 40,960 / 156 | 262.6 | 219 / 219 | 123 / 0 | mixed throughput |
| 256 | 3, silent | 1.281 | 1.768 | 0.776 | 94,792 / 894,072 | 40,960 / 153 | 267.7 | 219 / 219 | 129 / 0 | mixed p95, mixed throughput |
| 256 | 4, private | 1.081 | 1.391 | 0.855 | 94,792 / 918,792 | 40,960 / 156 | 262.6 | 219 / 219 | 135 / 0 | mixed p95 |
| 1,024 | 1, silent | 1.206 | 0.970 | 0.982 | 337,872 / 1,701,592 | 61,440 / 257 | 239.1 | 877 / 877 | 178 / 0 | None |
| 1,024 | 2, private | 0.779 | 0.896 | 1.115 | 337,872 / 1,738,672 | 65,536 / 260 | 252.1 | 877 / 877 | 176 / 0 | None |
| 1,024 | 3, silent | 1.064 | 1.126 | 0.940 | 337,872 / 1,746,912 | 61,440 / 257 | 239.1 | 877 / 877 | 179 / 0 | None |
| 1,024 | 4, private | 0.919 | 0.868 | 1.090 | 337,872 / 1,734,552 | 61,440 / 256 | 240.0 | 877 / 877 | 176 / 0 | None |
| 4,096 | 1, silent | 1.184 | 1.391 | 0.786 | 1,289,592 / 4,144,752 | 114,688 / 447 | 256.6 | 3,510 / 3,510 | 285 / 0 | mixed p95, mixed throughput |
| 4,096 | 2, private | 0.908 | 0.969 | 1.060 | 1,289,592 / 4,095,312 | 110,592 / 447 | 247.4 | 3,510 / 3,510 | 276 / 0 | None |
| 4,096 | 3, silent | 1.270 | 0.958 | 1.119 | 1,289,592 / 4,070,592 | 110,592 / 447 | 247.4 | 3,510 / 3,510 | 281 / 0 | None |
| 4,096 | 4, private | 0.658 | 0.924 | 1.160 | 1,289,592 / 4,045,872 | 110,592 / 450 | 245.8 | 3,510 / 3,510 | 279 / 0 | None |

5/12 repetitions missed at least one provisional flag. The JSON report preserves each arm's measurements and individual checks.

Python 3.9.6, SQLite 3.39.5, macOS-13.7.8-x86_64-i386-64bit. Schema 8, store source SHA-256 `7f4276340281b9389ccc61e58afa0c0ca93d75a7e08f464597066543d507c926`. Elapsed time 96.2 s.

The fixture is synthetic and measures one host and runtime. Mixed throughput includes starting workers and waiting for the prune previews. WAL bytes are file sizes before the explicit checkpoint, and checkpointed DB growth includes index and page allocation. Expiry cleanup deletes rows while SQLite retains allocated pages for reuse.

Re-run with `python3 -I experiments/private_retention_scale.py --output /tmp/private_retention_scale`.
