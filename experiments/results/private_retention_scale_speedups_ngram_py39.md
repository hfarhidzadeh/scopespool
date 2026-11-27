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
| 256 / 2 | 7.68, 8.35 / 8.70, 8.90 | 13.79, 39.71 / 15.04, 40.84 | 142.00 / 125.23 | 20.65, 10.47 / 20.70, 10.43 | 1.08 / 4.31 | 0.92 / 3.08 |
| 1,024 / 4 | 22.86, 25.31 / 24.12, 24.45 | 161.11, 280.63 / 161.40, 286.86 | 27.35 / 26.44 | 350.90, 41.22 / 349.73, 38.58 | 1.04 / 5.11 | 1.50 / 4.04 |
| 4,096 / 8 | 80.42, 91.33 / 81.71, 92.02 | 1944.45, 2924.78 / 2151.24, 3025.63 | 4.84 / 4.46 | 4677.39, 173.48 / 5710.19, 179.43 | 1.69 / 5.83 | 3.85 / 7.81 |

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
| 256 | 1, silent | 1.218 | 0.986 | 0.908 | 1,207,192 / 2,092,992 | 40,960 / 164 | 249.8 | 219 / 219 | 127 / 0 | None |
| 256 | 2, private | 0.992 | 0.678 | 1.125 | 1,207,192 / 2,088,872 | 40,960 / 170 | 240.9 | 219 / 219 | 122 / 0 | None |
| 256 | 3, silent | 1.007 | 1.080 | 0.879 | 1,207,192 / 2,084,752 | 40,960 / 165 | 248.2 | 219 / 219 | 135 / 0 | None |
| 256 | 4, private | 1.133 | 1.282 | 0.844 | 1,207,192 / 2,080,632 | 40,960 / 168 | 243.8 | 219 / 219 | 130 / 0 | None |
| 1,024 | 1, silent | 0.839 | 1.018 | 0.896 | 337,872 / 1,738,672 | 65,536 / 268 | 244.5 | 877 / 877 | 184 / 0 | None |
| 1,024 | 2, private | 1.009 | 0.913 | 1.041 | 337,872 / 1,775,752 | 65,536 / 265 | 247.3 | 877 / 877 | 180 / 0 | None |
| 1,024 | 3, silent | 0.965 | 1.142 | 0.891 | 337,872 / 1,771,632 | 65,536 / 266 | 246.4 | 877 / 877 | 186 / 0 | None |
| 1,024 | 4, private | 1.105 | 0.962 | 0.965 | 337,872 / 1,771,632 | 65,536 / 264 | 248.2 | 877 / 877 | 180 / 0 | None |
| 4,096 | 1, silent | 1.154 | 0.942 | 0.994 | 2,879,912 / 807,552 | 110,592 / 449 | 246.3 | 3,510 / 3,510 | 276 / 0 | None |
| 4,096 | 2, private | 0.873 | 1.385 | 0.567 | 2,879,912 / 918,792 | 110,592 / 446 | 248.0 | 3,510 / 3,510 | 280 / 0 | mixed p95, mixed throughput |
| 4,096 | 3, silent | 1.165 | 1.004 | 0.931 | 2,879,912 / 869,352 | 110,592 / 448 | 246.9 | 3,510 / 3,510 | 284 / 0 | None |
| 4,096 | 4, private | 0.867 | 1.065 | 0.913 | 2,879,912 / 922,912 | 110,592 / 447 | 247.4 | 3,510 / 3,510 | 275 / 0 | None |

1/12 repetitions missed at least one provisional flag. The JSON report preserves each arm's measurements and individual checks.

Python 3.9.6, SQLite 3.39.5, macOS-13.7.8-x86_64-i386-64bit. Schema 8, store source SHA-256 `40258276b32c693787e7addfd3b0226f9bcec53b3ae87dcacc80333467d7c337`. Elapsed time 216.5 s.

The fixture is synthetic and measures one host and runtime. Mixed throughput includes starting workers and waiting for the prune previews. WAL bytes are file sizes before the explicit checkpoint, and checkpointed DB growth includes index and page allocation. Expiry cleanup deletes rows while SQLite retains allocated pages for reuse.

Re-run with `python3 -I experiments/private_retention_scale.py --output /tmp/private_retention_scale`.
