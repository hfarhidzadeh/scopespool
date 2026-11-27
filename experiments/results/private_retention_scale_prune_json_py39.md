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
| 256 / 2 | 3.29, 5.01 / 4.32, 6.76 | 5.38, 16.81 / 7.03, 18.90 | 305.91 / 248.50 | 8.66, 7.60 / 8.91, 5.82 | 1.07 / 5.53 | 1.17 / 3.20 |
| 1,024 / 4 | 9.20, 13.19 / 9.67, 13.68 | 64.82, 105.96 / 68.92, 125.67 | 66.19 / 61.39 | 25.57, 24.02 / 23.58, 21.49 | 0.93 / 5.55 | 1.80 / 4.11 |
| 4,096 / 8 | 33.55, 41.12 / 34.88, 43.11 | 574.92, 1249.25 / 530.46, 1225.56 | 12.61 / 13.50 | 90.74, 96.69 / 94.01, 115.88 | 1.10 / 6.29 | 4.16 / 6.70 |

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
| 256 | 1, silent | 1.316 | 1.776 | 0.870 | 94,792 / 894,072 | 40,960 / 153 | 267.7 | 219 / 219 | 131 / 0 | serial p95, mixed p95 |
| 256 | 2, private | 1.455 | 1.167 | 0.763 | 94,792 / 922,912 | 40,960 / 156 | 262.6 | 219 / 219 | 123 / 0 | serial p95, mixed throughput |
| 256 | 3, silent | 1.283 | 0.898 | 0.768 | 94,792 / 894,072 | 40,960 / 153 | 267.7 | 219 / 219 | 129 / 0 | mixed throughput |
| 256 | 4, private | 1.225 | 0.995 | 0.817 | 94,792 / 918,792 | 40,960 / 156 | 262.6 | 219 / 219 | 135 / 0 | None |
| 1,024 | 1, silent | 1.201 | 1.135 | 0.891 | 337,872 / 1,705,712 | 61,440 / 257 | 239.1 | 877 / 877 | 178 / 0 | None |
| 1,024 | 2, private | 1.034 | 1.289 | 0.939 | 337,872 / 1,746,912 | 65,536 / 260 | 252.1 | 877 / 877 | 176 / 0 | None |
| 1,024 | 3, silent | 1.167 | 1.261 | 0.924 | 337,872 / 1,722,192 | 61,440 / 257 | 239.1 | 877 / 877 | 179 / 0 | None |
| 1,024 | 4, private | 0.961 | 0.992 | 0.955 | 337,872 / 1,713,952 | 61,440 / 256 | 240.0 | 877 / 877 | 176 / 0 | None |
| 4,096 | 1, silent | 1.314 | 1.152 | 0.954 | 1,289,592 / 4,082,952 | 110,592 / 447 | 247.4 | 3,510 / 3,510 | 285 / 0 | serial p95 |
| 4,096 | 2, private | 0.685 | 0.845 | 1.254 | 1,289,592 / 4,078,832 | 110,592 / 447 | 247.4 | 3,510 / 3,510 | 276 / 0 | None |
| 4,096 | 3, silent | 1.257 | 0.855 | 1.163 | 1,289,592 / 4,037,632 | 110,592 / 447 | 247.4 | 3,510 / 3,510 | 281 / 0 | None |
| 4,096 | 4, private | 0.857 | 1.128 | 0.991 | 1,289,592 / 4,045,872 | 110,592 / 450 | 245.8 | 3,510 / 3,510 | 279 / 0 | None |

4/12 repetitions missed at least one provisional flag. The JSON report preserves each arm's measurements and individual checks.

Python 3.9.6, SQLite 3.39.5, macOS-13.7.8-x86_64-i386-64bit. Schema 8, store source SHA-256 `7f4276340281b9389ccc61e58afa0c0ca93d75a7e08f464597066543d507c926`. Elapsed time 94.5 s.

The fixture is synthetic and measures one host and runtime. Mixed throughput includes starting workers and waiting for the prune previews. WAL bytes are file sizes before the explicit checkpoint, and checkpointed DB growth includes index and page allocation. Expiry cleanup deletes rows while SQLite retains allocated pages for reuse.

Re-run with `python3 -I experiments/private_retention_scale.py --output /tmp/private_retention_scale`.
