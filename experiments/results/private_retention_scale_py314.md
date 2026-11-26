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
| 256 / 2 | 5.84, 6.19 / 7.76, 9.45 | 11.34, 38.08 / 13.83, 42.13 | 145.45 / 129.21 | 25.81, 10.26 / 28.22, 9.07 | 1.00 / 3.67 | 1.36 / 3.12 |
| 1,024 / 4 | 18.70, 19.74 / 20.77, 23.53 | 174.68, 405.27 / 188.04, 388.11 | 23.69 / 23.16 | 412.06, 35.10 / 330.97, 32.74 | 0.97 / 4.07 | 3.07 / 5.67 |
| 4,096 / 8 | 71.74, 75.10 / 75.58, 79.10 | 1606.75, 4344.76 / 2465.69, 4624.95 | 3.88 / 3.48 | 3337.02, 139.17 / 3944.13, 129.03 | 1.15 / 5.04 | 10.00 / 13.23 |

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
| 256 | 1, silent | 1.512 | 0.947 | 0.885 | 94,792 / 894,072 | 40,960 / 153 | 267.7 | 219 / 219 | 131 / 0 | serial p95 |
| 256 | 2, private | 1.395 | 1.014 | 0.926 | 94,792 / 918,792 | 40,960 / 156 | 262.6 | 219 / 219 | 123 / 0 | serial p95 |
| 256 | 3, silent | 1.441 | 1.375 | 0.786 | 94,792 / 894,072 | 40,960 / 153 | 267.7 | 219 / 219 | 129 / 0 | serial p95, mixed p95, mixed throughput |
| 256 | 4, private | 1.546 | 1.208 | 0.905 | 94,792 / 914,672 | 40,960 / 156 | 262.6 | 219 / 219 | 135 / 0 | serial p95 |
| 1,024 | 1, silent | 1.090 | 0.783 | 0.997 | 337,872 / 1,697,472 | 61,440 / 257 | 239.1 | 877 / 877 | 178 / 0 | None |
| 1,024 | 2, private | 1.210 | 1.050 | 0.915 | 337,872 / 1,746,912 | 65,536 / 260 | 252.1 | 877 / 877 | 176 / 0 | None |
| 1,024 | 3, silent | 1.194 | 1.289 | 0.986 | 337,872 / 1,734,552 | 61,440 / 257 | 239.1 | 877 / 877 | 179 / 0 | None |
| 1,024 | 4, private | 1.227 | 0.704 | 1.087 | 337,872 / 1,722,192 | 61,440 / 256 | 240.0 | 877 / 877 | 176 / 0 | None |
| 4,096 | 1, silent | 1.101 | 1.107 | 0.825 | 1,289,592 / 4,041,752 | 110,592 / 447 | 247.4 | 3,510 / 3,510 | 285 / 0 | None |
| 4,096 | 2, private | 1.070 | 1.190 | 0.916 | 1,289,592 / 4,054,112 | 110,592 / 447 | 247.4 | 3,510 / 3,510 | 276 / 0 | None |
| 4,096 | 3, silent | 1.041 | 1.025 | 0.741 | 1,289,592 / 4,070,592 | 110,592 / 447 | 247.4 | 3,510 / 3,510 | 281 / 0 | mixed throughput |
| 4,096 | 4, private | 0.999 | 0.878 | 0.879 | 1,289,592 / 4,095,312 | 106,496 / 450 | 236.7 | 3,510 / 3,510 | 279 / 0 | None |

5/12 repetitions missed at least one provisional flag. The JSON report preserves each arm's measurements and individual checks.

Python 3.14.8, SQLite 3.53.4, macOS-13.7.8-x86_64-i386-64bit-Mach-O. Schema 8, store source SHA-256 `55bfa04a5e441c1b53d1bc6c53986e627ee49e16658dc50b4e93dba4c3faa99b`. Elapsed time 237.4 s.

The fixture is synthetic and measures one host and runtime. Mixed throughput includes starting workers and waiting for the prune previews. WAL bytes are file sizes before the explicit checkpoint, and checkpointed DB growth includes index and page allocation. Expiry cleanup deletes rows while SQLite retains allocated pages for reuse.

Re-run with `python3 -I experiments/private_retention_scale.py --output /tmp/private_retention_scale`.
