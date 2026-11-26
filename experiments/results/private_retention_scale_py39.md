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
| 256 / 2 | 6.13, 7.09 / 7.43, 8.68 | 13.52, 30.68 / 13.93, 38.96 | 146.96 / 136.23 | 25.37, 11.79 / 27.26, 9.58 | 1.05 / 4.47 | 1.46 / 3.48 |
| 1,024 / 4 | 20.25, 23.72 / 21.40, 27.96 | 156.09, 313.05 / 151.25, 317.49 | 27.57 / 26.22 | 287.79, 44.53 / 287.53, 37.94 | 1.65 / 5.16 | 5.03 / 7.08 |
| 4,096 / 8 | 86.80, 112.69 / 80.90, 95.74 | 1400.74, 3620.83 / 1889.06, 3773.05 | 4.85 / 4.24 | 3614.98, 177.29 / 3764.76, 151.57 | 1.76 / 7.10 | 11.67 / 16.06 |

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
| 256 | 1, silent | 0.973 | 0.680 | 1.162 | 94,792 / 894,072 | 40,960 / 153 | 267.7 | 219 / 219 | 131 / 0 | None |
| 256 | 2, private | 1.121 | 1.552 | 0.846 | 94,792 / 918,792 | 40,960 / 156 | 262.6 | 219 / 219 | 123 / 0 | mixed p95 |
| 256 | 3, silent | 2.249 | 1.359 | 0.768 | 94,792 / 894,072 | 40,960 / 153 | 267.7 | 219 / 219 | 129 / 0 | serial p95, mixed p95, mixed throughput |
| 256 | 4, private | 1.181 | 1.346 | 0.983 | 94,792 / 918,792 | 40,960 / 156 | 262.6 | 219 / 219 | 135 / 0 | None |
| 1,024 | 1, silent | 1.166 | 1.034 | 1.052 | 337,872 / 1,726,312 | 61,440 / 257 | 239.1 | 877 / 877 | 178 / 0 | None |
| 1,024 | 2, private | 0.603 | 1.007 | 0.682 | 337,872 / 1,759,272 | 65,536 / 260 | 252.1 | 877 / 877 | 176 / 0 | mixed throughput |
| 1,024 | 3, silent | 1.280 | 0.982 | 0.973 | 337,872 / 1,718,072 | 61,440 / 257 | 239.1 | 877 / 877 | 179 / 0 | None |
| 1,024 | 4, private | 0.878 | 0.993 | 0.979 | 337,872 / 1,701,592 | 61,440 / 256 | 240.0 | 877 / 877 | 176 / 0 | None |
| 4,096 | 1, silent | 1.802 | 0.901 | 0.851 | 1,289,592 / 4,041,752 | 110,592 / 447 | 247.4 | 3,510 / 3,510 | 285 / 0 | serial p95 |
| 4,096 | 2, private | 0.717 | 1.210 | 0.901 | 1,289,592 / 4,078,832 | 110,592 / 447 | 247.4 | 3,510 / 3,510 | 276 / 0 | None |
| 4,096 | 3, silent | 0.446 | 1.091 | 0.876 | 1,289,592 / 4,082,952 | 110,592 / 447 | 247.4 | 3,510 / 3,510 | 281 / 0 | None |
| 4,096 | 4, private | 0.866 | 1.002 | 0.855 | 1,289,592 / 4,041,752 | 110,592 / 450 | 245.8 | 3,510 / 3,510 | 279 / 0 | None |

4/12 repetitions missed at least one provisional flag. The JSON report preserves each arm's measurements and individual checks.

Python 3.9.6, SQLite 3.39.5, macOS-13.7.8-x86_64-i386-64bit. Schema 8, store source SHA-256 `55bfa04a5e441c1b53d1bc6c53986e627ee49e16658dc50b4e93dba4c3faa99b`. Elapsed time 230.3 s.

The fixture is synthetic and measures one host and runtime. Mixed throughput includes starting workers and waiting for the prune previews. WAL bytes are file sizes before the explicit checkpoint, and checkpointed DB growth includes index and page allocation. Expiry cleanup deletes rows while SQLite retains allocated pages for reuse.

Re-run with `python3 -I experiments/private_retention_scale.py --output /tmp/private_retention_scale`.
