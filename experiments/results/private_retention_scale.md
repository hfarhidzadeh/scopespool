# Private retention scale pilot

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
| 256 / 2 | 7.97, 9.28 / 9.42, 10.73 | 16.39, 45.22 / 17.05, 54.53 | 109.28 / 104.07 | 31.56, 17.12 / 36.52, 12.95 | 1.10 / 4.95 | 1.89 / 4.27 |
| 1,024 / 4 | 26.43, 28.10 / 27.72, 30.65 | 252.23, 490.96 / 265.15, 494.91 | 16.74 / 16.42 | 503.85, 55.59 / 499.03, 48.56 | 1.53 / 5.11 | 4.68 / 7.35 |
| 4,096 / 8 | 103.22, 121.69 / 103.04, 116.15 | 2767.93, 5599.61 / 3281.61, 5758.17 | 2.85 / 2.62 | 5655.48, 225.44 / 5546.81, 195.27 | 1.22 / 7.06 | 15.03 / 19.72 |

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
| 256 | 1, silent | 1.403 | 1.449 | 0.948 | 94,792 / 894,072 | 40,960 / 153 | 267.7 | 219 / 219 | 131 / 0 | serial p95, mixed p95 |
| 256 | 2, private | 1.248 | 1.213 | 0.989 | 94,792 / 918,792 | 40,960 / 156 | 262.6 | 219 / 219 | 123 / 0 | None |
| 256 | 3, silent | 1.078 | 1.204 | 0.930 | 94,792 / 889,952 | 40,960 / 153 | 267.7 | 219 / 219 | 129 / 0 | None |
| 256 | 4, private | 1.119 | 1.096 | 0.923 | 94,792 / 914,672 | 40,960 / 156 | 262.6 | 219 / 219 | 135 / 0 | None |
| 1,024 | 1, silent | 1.147 | 0.991 | 0.939 | 337,872 / 1,705,712 | 61,440 / 257 | 239.1 | 877 / 877 | 178 / 0 | None |
| 1,024 | 2, private | 1.013 | 0.967 | 0.993 | 337,872 / 1,746,912 | 65,536 / 260 | 252.1 | 877 / 877 | 176 / 0 | None |
| 1,024 | 3, silent | 0.669 | 1.064 | 0.890 | 337,872 / 1,722,192 | 65,536 / 257 | 255.0 | 877 / 877 | 179 / 0 | None |
| 1,024 | 4, private | 1.119 | 1.053 | 0.990 | 337,872 / 1,705,712 | 61,440 / 256 | 240.0 | 877 / 877 | 176 / 0 | None |
| 4,096 | 1, silent | 0.803 | 1.036 | 1.006 | 1,289,592 / 4,066,472 | 110,592 / 447 | 247.4 | 3,510 / 3,510 | 285 / 0 | None |
| 4,096 | 2, private | 0.890 | 1.051 | 0.981 | 1,289,592 / 4,078,832 | 110,592 / 447 | 247.4 | 3,510 / 3,510 | 276 / 0 | None |
| 4,096 | 3, silent | 1.275 | 0.983 | 0.847 | 1,289,592 / 4,082,952 | 110,592 / 447 | 247.4 | 3,510 / 3,510 | 281 / 0 | None |
| 4,096 | 4, private | 0.888 | 1.060 | 0.809 | 1,289,592 / 4,054,112 | 110,592 / 450 | 245.8 | 3,510 / 3,510 | 279 / 0 | None |

1/12 repetitions missed at least one provisional flag. The JSON report preserves each arm's measurements and individual checks.

Python 3.9.6, SQLite 3.39.5, macOS-13.7.8-x86_64-i386-64bit. Schema 8, store source SHA-256 `a8661cdbcb3af3e0407aa812783a6a4157f7ae89b99269d661b170f3c2fa88dd`. Elapsed time 325.3 s.

The fixture is synthetic and measures one host and runtime. Mixed throughput includes starting workers and waiting for the prune previews. WAL bytes are file sizes before the explicit checkpoint, and checkpointed DB growth includes index and page allocation. Expiry cleanup deletes rows while SQLite retains allocated pages for reuse.

Re-run with `python3 -I experiments/private_retention_scale.py --output /tmp/private_retention_scale`.
