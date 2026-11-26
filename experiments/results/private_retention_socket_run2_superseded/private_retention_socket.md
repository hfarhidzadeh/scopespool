# Private retention over the Unix socket

Sizes (memories/readers) 256/2, 1,024/4, 4,096/8; 4 paired repetitions.

**Acceptance gate: fail (a, b failed; first failing: 4,096 memories, pair 2).** Pre-registered in the script's docstring; each criterion must hold in every pair.

| Criterion | Pairs held |
| --- | ---: |
| (a) every request and concurrent prune preview completed in both arms | 10/12 |
| (b) identical searches, observer probes, previews and applied prune between arms | 10/12 |
| (c) each private reader's list equals its own archived results; silent lists empty | 12/12 |
| (d) peer and outsider lists empty; private rows only for readers who searched privately | 12/12 |

The production client opens a new local socket for each call to a separate threaded ScopeSpool server process. Timings include connection setup, signed-token verification, JSON, store work and the decoded response. The harness seeds independent copies of a synthetic WAL database, starts the server, issues tokens, runs prune previews through the trusted local store alongside the concurrent socket reads, and applies the administrative prune outside the timed client calls.

Each arm runs 4 warmup and 24 serial searches, 12 concurrent searches per reader with 2 prune previews, and 6 personal-list calls per reader. Search limit 5. The peer, joint audience and disjoint viewer are queried before the workload, after the reads, and after pruning. Arm order alternates by repetition.

| Memories / readers | Pair | Mode | All requests OK / attempted | Serial p95 (ms) | Concurrent p95 (ms) | Successful concurrent calls/s | Preview p95 (ms) | Personal list p95 (ms) | Retained per reader |
| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 256 / 2 | 1 | silent | 81/81 | 7.93 | 13.33 | 218.53 | 11.65 | 3.42 | 0, 0 |
| 256 / 2 | 1 | private | 81/81 | 15.91 | 24.27 | 129.65 | 14.93 | 19.56 | 105, 50 |
| 256 / 2 | 2 | private | 81/81 | 20.08 | 20.16 | 143.21 | 11.85 | 10.84 | 99, 54 |
| 256 / 2 | 2 | silent | 81/81 | 8.09 | 11.82 | 212.23 | 11.47 | 3.63 | 0, 0 |
| 256 / 2 | 3 | silent | 81/81 | 6.89 | 12.54 | 218.42 | 10.24 | 4.01 | 0, 0 |
| 256 / 2 | 3 | private | 81/81 | 16.17 | 19.47 | 137.26 | 10.73 | 12.03 | 105, 49 |
| 256 / 2 | 4 | private | 81/81 | 17.65 | 19.36 | 146.68 | 10.81 | 11.92 | 105, 57 |
| 256 / 2 | 4 | silent | 81/81 | 7.01 | 11.05 | 227.08 | 10.98 | 3.64 | 0, 0 |
| 1,024 / 4 | 1 | silent | 117/117 | 12.51 | 103.64 | 53.31 | 49.00 | 3.48 | 0, 0, 0, 0 |
| 1,024 / 4 | 1 | private | 117/117 | 31.90 | 178.72 | 36.87 | 46.11 | 17.48 | 99, 53, 53, 50 |
| 1,024 / 4 | 2 | private | 117/117 | 35.71 | 110.09 | 49.81 | 41.03 | 11.66 | 103, 49, 49, 51 |
| 1,024 / 4 | 2 | silent | 117/117 | 12.10 | 120.57 | 49.44 | 39.58 | 3.31 | 0, 0, 0, 0 |
| 1,024 / 4 | 3 | silent | 117/117 | 11.97 | 94.78 | 54.57 | 41.35 | 3.20 | 0, 0, 0, 0 |
| 1,024 / 4 | 3 | private | 117/117 | 225.55 | 277.86 | 24.58 | 110.31 | 24.07 | 102, 53, 50, 49 |
| 1,024 / 4 | 4 | private | 117/117 | 85.25 | 336.25 | 15.73 | 114.06 | 36.80 | 100, 49, 52, 53 |
| 1,024 / 4 | 4 | silent | 117/117 | 43.65 | 546.07 | 12.61 | 646.03 | 8.22 | 0, 0, 0, 0 |
| 4,096 / 8 | 1 | silent | 189/189 | 95.37 | 3852.57 | 2.96 | 526.65 | 9.75 | 0, 0, 0, 0, 0, 0, 0, 0 |
| 4,096 / 8 | 1 | private | 189/189 | 184.48 | 3584.54 | 3.68 | 582.55 | 38.84 | 104, 52, 49, 49, 49, 51, 55, 54 |
| 4,096 / 8 | 2 | private | 188/189 | 123.90 | 3634.88 | 3.49 | 512.01 | 34.55 | 98, 50, 55, 55, 50, 49, 49, 48 |
| 4,096 / 8 | 2 | silent | 189/189 | 158.67 | 3800.33 | 3.37 | 477.43 | 6.43 | 0, 0, 0, 0, 0, 0, 0, 0 |
| 4,096 / 8 | 3 | silent | 189/189 | 121.98 | 3451.76 | 3.27 | 484.99 | 17.76 | 0, 0, 0, 0, 0, 0, 0, 0 |
| 4,096 / 8 | 3 | private | 189/189 | 295.00 | 3542.59 | 3.59 | 730.89 | 40.15 | 103, 49, 49, 49, 52, 55, 53, 48 |
| 4,096 / 8 | 4 | private | 188/189 | 111.95 | 3694.79 | 3.35 | 504.03 | 105.91 | 101, 55, 54, 49, 45, 49, 49, 54 |
| 4,096 / 8 | 4 | silent | 188/189 | 185.03 | 3399.23 | 3.59 | 516.83 | 7.09 | 0, 0, 0, 0, 0, 0, 0, 0 |

Latency percentiles summarize successful requests. Concurrent throughput divides successful searches by total wall time, including failed calls and worker startup. The JSON records client-visible errors and their latency separately. Results describe this local lexical fixture and runtime; latency and throughput are not gated.

Python 3.9.6, SQLite 3.39.5, macOS-13.7.8-x86_64-i386-64bit. Store SHA-256 `f88e788c1ef1c71ed3f5bbb0e12d7e9e57ffb5f37f0759225dc5dd835786c00d`. Server SHA-256 `dda5a98d6a374ac1dfc3c14eac930a52fd8fb0f824469391a49fe3c8bdccf0fd`. Elapsed time 375.3 s.
