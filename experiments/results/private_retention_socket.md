# Private retention over the Unix socket

Sizes (memories/readers) 256/2, 1,024/4, 4,096/8; 4 paired repetitions.

**Acceptance gate: pass.** Pre-registered in the script's docstring; each criterion must hold in every pair.

| Criterion | Pairs held |
| --- | ---: |
| (a) every request and concurrent prune preview completed in both arms | 12/12 |
| (b) identical searches, observer probes, previews and applied prune between arms | 12/12 |
| (c) each private reader's list equals its own archived results; silent lists empty | 12/12 |
| (d) peer and outsider lists empty; private rows only for readers who searched privately | 12/12 |

The production client opens a new local socket for each call to a separate threaded ScopeSpool server process. Timings include connection setup, signed-token verification, JSON, store work and the decoded response. The harness seeds independent copies of a synthetic WAL database, starts the server, issues tokens, runs prune previews through the trusted local store alongside the concurrent socket reads, and applies the administrative prune outside the timed client calls.

Each arm runs 4 warmup and 24 serial searches, 12 concurrent searches per reader with 2 prune previews, and 6 personal-list calls per reader. Search limit 5. The peer, joint audience and disjoint viewer are queried before the workload, after the reads, and after pruning. Arm order alternates by repetition.

| Memories / readers | Pair | Mode | All requests OK / attempted | Serial p95 (ms) | Concurrent p95 (ms) | Successful concurrent calls/s | Preview p95 (ms) | Personal list p95 (ms) | Retained per reader |
| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 256 / 2 | 1 | silent | 81/81 | 7.95 | 11.69 | 228.50 | 12.58 | 3.18 | 0, 0 |
| 256 / 2 | 1 | private | 81/81 | 22.50 | 17.86 | 151.12 | 11.35 | 28.90 | 105, 50 |
| 256 / 2 | 2 | private | 81/81 | 54.03 | 20.49 | 138.90 | 13.08 | 11.78 | 99, 54 |
| 256 / 2 | 2 | silent | 81/81 | 7.66 | 12.42 | 193.34 | 11.69 | 3.42 | 0, 0 |
| 256 / 2 | 3 | silent | 81/81 | 18.57 | 15.94 | 147.52 | 14.85 | 9.11 | 0, 0 |
| 256 / 2 | 3 | private | 81/81 | 24.01 | 28.90 | 102.34 | 10.27 | 16.79 | 105, 49 |
| 256 / 2 | 4 | private | 81/81 | 24.77 | 30.61 | 100.30 | 19.91 | 12.75 | 105, 57 |
| 256 / 2 | 4 | silent | 81/81 | 17.00 | 31.85 | 110.33 | 15.13 | 4.62 | 0, 0 |
| 1,024 / 4 | 1 | silent | 117/117 | 14.02 | 182.96 | 37.31 | 58.50 | 6.17 | 0, 0, 0, 0 |
| 1,024 / 4 | 1 | private | 117/117 | 26.45 | 111.72 | 50.01 | 39.11 | 12.06 | 99, 53, 53, 50 |
| 1,024 / 4 | 2 | private | 117/117 | 60.76 | 295.51 | 28.23 | 302.93 | 15.45 | 103, 49, 49, 51 |
| 1,024 / 4 | 2 | silent | 117/117 | 13.63 | 134.12 | 44.66 | 40.42 | 4.07 | 0, 0, 0, 0 |
| 1,024 / 4 | 3 | silent | 117/117 | 32.30 | 304.30 | 31.19 | 52.80 | 3.91 | 0, 0, 0, 0 |
| 1,024 / 4 | 3 | private | 117/117 | 34.03 | 151.23 | 45.75 | 54.85 | 20.97 | 102, 53, 50, 49 |
| 1,024 / 4 | 4 | private | 117/117 | 35.48 | 126.12 | 46.92 | 43.06 | 39.95 | 100, 49, 52, 53 |
| 1,024 / 4 | 4 | silent | 117/117 | 21.14 | 274.95 | 32.48 | 50.37 | 3.19 | 0, 0, 0, 0 |
| 4,096 / 8 | 1 | silent | 189/189 | 38.90 | 1371.68 | 9.20 | 238.42 | 3.70 | 0, 0, 0, 0, 0, 0, 0, 0 |
| 4,096 / 8 | 1 | private | 189/189 | 47.27 | 1442.30 | 8.71 | 189.89 | 14.83 | 104, 52, 49, 49, 49, 51, 55, 54 |
| 4,096 / 8 | 2 | private | 189/189 | 84.59 | 1685.76 | 7.38 | 466.63 | 37.34 | 98, 50, 55, 55, 50, 49, 49, 48 |
| 4,096 / 8 | 2 | silent | 189/189 | 182.26 | 1520.04 | 9.37 | 258.97 | 11.97 | 0, 0, 0, 0, 0, 0, 0, 0 |
| 4,096 / 8 | 3 | silent | 189/189 | 147.66 | 1505.53 | 9.61 | 112.27 | 3.83 | 0, 0, 0, 0, 0, 0, 0, 0 |
| 4,096 / 8 | 3 | private | 189/189 | 54.47 | 1459.50 | 10.28 | 250.14 | 14.54 | 103, 49, 49, 49, 52, 55, 53, 48 |
| 4,096 / 8 | 4 | private | 189/189 | 80.57 | 1431.00 | 8.61 | 331.79 | 12.25 | 101, 55, 54, 49, 49, 49, 49, 54 |
| 4,096 / 8 | 4 | silent | 189/189 | 43.84 | 1405.82 | 8.32 | 221.65 | 2.37 | 0, 0, 0, 0, 0, 0, 0, 0 |

Latency percentiles summarize successful requests. Concurrent throughput divides successful searches by total wall time, including failed calls and worker startup. The JSON records client-visible errors and their latency separately. Results describe this local lexical fixture and runtime; latency and throughput are not gated.

Python 3.9.6, SQLite 3.39.5, macOS-13.7.8-x86_64-i386-64bit. Store SHA-256 `f88e788c1ef1c71ed3f5bbb0e12d7e9e57ffb5f37f0759225dc5dd835786c00d`. Server SHA-256 `afceffd4a6532747cbcbc53ddaca6f67166141825960188074392b48cdb40ef8`. Elapsed time 176.1 s.
