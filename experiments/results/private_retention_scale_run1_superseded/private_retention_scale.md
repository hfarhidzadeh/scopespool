# Private retention scale pilot

**Behavior checks passed in 12/12 paired repetitions.** Silent and private arms compared exact search results, preview and applied prune results, and observer rankings for an overlapping peer, a joint audience, and a disjoint viewer. Each private arm checked the expected retained entries, private row counts, and expiry cleanup. Search and preview comparisons include matched calls that completed in both modes.

**All calls completed in 10/12 pairs.** The initial full run aborted on a SQLite lock error during a private search in the 4,096-memory, eight-reader fixture. The eight smaller pairs finished before the abort, but the earlier runner emitted results only after the full run. This rerun records lock errors and failed wait times without retries.

## Fixed workload

Each size starts from a shared synthetic fixture copied into independent WAL databases. Mode order alternates across repetitions. Each pair uses the same queries in both modes. Each arm runs 4 warmup and 24 serial searches. Before and after one applied prune, each reader makes 6 and 3 concurrent searches, respectively, alongside 2 prune previews per phase. The personal list receives 12 timed reads. Cleanup runs with the private access clock advanced 91 days.

The local provisional flags allow private/silent p95 ratios up to 1.30 in serial and 1.35 in the mixed phase, throughput at least 0.80 of silent, at most 1,024 added checkpointed bytes per private row, and at most 50 ms for private cleanup. These flags identify workloads to investigate before planning a release.

## Results by workload

Values are medians across repetitions. Each cell lists silent / private values. Search and preview p50/p95 cover successful calls. Throughput counts successful searches over all elapsed time, including time spent waiting on failed calls.

| Memories / readers | Serial p50 / p95 (ms) | Mixed p50 / p95 (ms) | Successful mixed searches/s | Prune preview p95 / apply (ms) | Personal list p95 (ms) | Cleanup (ms) |
| --- | --- | --- | ---: | --- | ---: | ---: |
| 256 / 2 | 8.00, 11.29 / 7.36, 10.65 | 12.94, 40.35 / 7.47, 70.22 | 124.70 / 120.56 | 28.99, 14.53 / 12.22, 12.39 | 2.08 / 5.03 | 1.92 / 4.18 |
| 1,024 / 4 | 32.02, 104.52 / 27.64, 50.11 | 213.31, 642.24 / 28.24, 654.96 | 16.12 / 27.20 | 464.84, 158.14 / 78.02, 63.53 | 2.68 / 17.27 | 7.03 / 7.89 |
| 4,096 / 8 | 88.30, 316.90 / 83.88, 107.53 | 1488.80, 3786.53 / 90.47, 2727.60 | 4.45 / 10.40 | 3644.84, 174.02 / 240.73, 225.35 | 3.75 / 9.11 | 13.99 / 15.86 |

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
| 4,096 | 1 | 72/72 / 71/72 | 5329.30 | 1 |
| 4,096 | 2 | 72/72 / 72/72 | n/a | 0 |
| 4,096 | 3 | 72/72 / 71/72 | 5308.71 | 1 |
| 4,096 | 4 | 72/72 / 72/72 | n/a | 0 |

## Paired ratios and storage

| Memories | Pair, first arm | Serial p95 ratio | Mixed p95 ratio | Throughput ratio | WAL bytes, silent / private | Added DB bytes / private rows | Added bytes/row | Archived, silent / private | Personal results before / after expiry | Flags missed |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 256 | 1, silent | 1.205 | 1.919 | 0.919 | 94,792 / 889,952 | 40,960 / 153 | 267.7 | 219 / 219 | 131 / 0 | mixed p95 |
| 256 | 2, private | 1.160 | 2.015 | 0.797 | 94,792 / 918,792 | 40,960 / 156 | 262.6 | 219 / 219 | 123 / 0 | mixed p95, mixed throughput |
| 256 | 3, silent | 0.688 | 0.729 | 1.219 | 94,792 / 894,072 | 40,960 / 153 | 267.7 | 219 / 219 | 129 / 0 | None |
| 256 | 4, private | 0.451 | 1.679 | 1.173 | 94,792 / 914,672 | 40,960 / 156 | 262.6 | 219 / 219 | 135 / 0 | mixed p95 |
| 1,024 | 1, silent | 1.236 | 1.091 | 2.008 | 337,872 / 1,759,272 | 65,536 / 257 | 255.0 | 877 / 877 | 178 / 0 | None |
| 1,024 | 2, private | 0.279 | 0.829 | 1.735 | 337,872 / 1,746,912 | 65,536 / 260 | 252.1 | 877 / 877 | 176 / 0 | None |
| 1,024 | 3, silent | 0.198 | 0.801 | 1.797 | 337,872 / 1,726,312 | 61,440 / 257 | 239.1 | 877 / 877 | 179 / 0 | None |
| 1,024 | 4, private | 2.510 | 1.856 | 1.414 | 337,872 / 1,788,112 | 65,536 / 256 | 256.0 | 877 / 877 | 176 / 0 | serial p95, mixed p95 |
| 4,096 | 1, silent | 0.444 | 0.609 | 1.974 | 1,289,592 / 4,074,712 | 110,592 / 442 | 250.2 | 3,510 / 3,510 | 280 / 0 | None |
| 4,096 | 2, private | 0.721 | 0.769 | 2.458 | 1,289,592 / 4,144,752 | 106,496 / 447 | 238.2 | 3,510 / 3,510 | 276 / 0 | None |
| 4,096 | 3, silent | 0.228 | 0.663 | 2.585 | 1,289,592 / 4,054,112 | 110,592 / 442 | 250.2 | 3,510 / 3,510 | 277 / 0 | None |
| 4,096 | 4, private | 0.336 | 0.877 | 2.463 | 1,289,592 / 4,124,152 | 110,592 / 450 | 245.8 | 3,510 / 3,510 | 279 / 0 | None |

4/12 repetitions missed at least one provisional flag. The JSON report preserves each arm's measurements and individual checks.

Python 3.9.6, SQLite 3.39.5, macOS-13.7.8-x86_64-i386-64bit. Schema 8, store source SHA-256 `044195188dce98d43d88be88ae395f25eb3a91e30132cc459c63e23295d5e19d`. Elapsed time 217.9 s.

The fixture is synthetic and measures one host and runtime. Mixed throughput includes starting workers and waiting for the prune previews. WAL bytes are file sizes before the explicit checkpoint, and checkpointed DB growth includes index and page allocation. Expiry cleanup deletes rows while SQLite retains allocated pages for reuse.

Re-run with `python3 -I experiments/private_retention_scale.py --output /tmp/private_retention_scale`.
