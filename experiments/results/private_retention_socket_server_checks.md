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
| 256 / 2 | 1 | silent | 81/81 | 5.87 | 18.36 | 168.39 | 9.76 | 2.15 | 0, 0 |
| 256 / 2 | 1 | private | 81/81 | 20.61 | 23.60 | 120.11 | 10.03 | 14.56 | 105, 50 |
| 256 / 2 | 2 | private | 81/81 | 21.53 | 23.48 | 117.64 | 13.32 | 12.86 | 99, 54 |
| 256 / 2 | 2 | silent | 81/81 | 7.96 | 16.54 | 184.48 | 9.20 | 2.04 | 0, 0 |
| 256 / 2 | 3 | silent | 81/81 | 6.25 | 14.71 | 210.85 | 7.92 | 2.09 | 0, 0 |
| 256 / 2 | 3 | private | 81/81 | 17.32 | 21.47 | 140.25 | 9.23 | 13.84 | 105, 49 |
| 256 / 2 | 4 | private | 81/81 | 19.81 | 21.11 | 133.00 | 9.81 | 16.91 | 105, 57 |
| 256 / 2 | 4 | silent | 81/81 | 7.06 | 12.53 | 198.65 | 9.72 | 2.43 | 0, 0 |
| 1,024 / 4 | 1 | silent | 117/117 | 20.79 | 148.89 | 35.54 | 64.69 | 2.19 | 0, 0, 0, 0 |
| 1,024 / 4 | 1 | private | 117/117 | 24.52 | 138.57 | 40.47 | 47.23 | 13.18 | 99, 53, 53, 50 |
| 1,024 / 4 | 2 | private | 117/117 | 22.37 | 110.07 | 45.90 | 26.29 | 14.30 | 103, 49, 49, 51 |
| 1,024 / 4 | 2 | silent | 117/117 | 13.33 | 119.20 | 46.93 | 24.65 | 2.08 | 0, 0, 0, 0 |
| 1,024 / 4 | 3 | silent | 117/117 | 13.90 | 101.65 | 48.73 | 26.09 | 2.32 | 0, 0, 0, 0 |
| 1,024 / 4 | 3 | private | 117/117 | 21.23 | 106.70 | 48.52 | 31.88 | 11.67 | 102, 53, 50, 49 |
| 1,024 / 4 | 4 | private | 117/117 | 22.12 | 121.43 | 46.40 | 31.02 | 13.04 | 100, 49, 52, 53 |
| 1,024 / 4 | 4 | silent | 117/117 | 12.70 | 109.73 | 47.86 | 25.50 | 2.17 | 0, 0, 0, 0 |
| 4,096 / 8 | 1 | silent | 189/189 | 38.04 | 1585.28 | 8.19 | 161.85 | 2.25 | 0, 0, 0, 0, 0, 0, 0, 0 |
| 4,096 / 8 | 1 | private | 189/189 | 45.30 | 1420.71 | 7.46 | 176.97 | 14.44 | 104, 52, 49, 49, 49, 51, 55, 54 |
| 4,096 / 8 | 2 | private | 189/189 | 45.49 | 1514.02 | 8.10 | 167.77 | 12.68 | 98, 50, 55, 55, 50, 49, 49, 48 |
| 4,096 / 8 | 2 | silent | 189/189 | 38.14 | 1530.66 | 8.80 | 119.22 | 2.21 | 0, 0, 0, 0, 0, 0, 0, 0 |
| 4,096 / 8 | 3 | silent | 189/189 | 37.91 | 1502.92 | 7.69 | 180.95 | 2.35 | 0, 0, 0, 0, 0, 0, 0, 0 |
| 4,096 / 8 | 3 | private | 189/189 | 48.64 | 1554.91 | 8.36 | 102.12 | 15.04 | 103, 49, 49, 49, 52, 55, 53, 48 |
| 4,096 / 8 | 4 | private | 189/189 | 46.84 | 1537.79 | 7.27 | 161.74 | 10.68 | 101, 55, 54, 49, 49, 49, 49, 54 |
| 4,096 / 8 | 4 | silent | 189/189 | 37.84 | 1447.55 | 7.77 | 100.42 | 3.18 | 0, 0, 0, 0, 0, 0, 0, 0 |

Latency percentiles summarize successful requests. Concurrent throughput divides successful searches by total wall time, including failed calls and worker startup. The JSON records client-visible errors and their latency separately. Results describe this local lexical fixture and runtime; latency and throughput are not gated.

Python 3.9.6, SQLite 3.39.5, macOS-13.7.8-x86_64-i386-64bit. Store SHA-256 `7f4276340281b9389ccc61e58afa0c0ca93d75a7e08f464597066543d507c926`. Server SHA-256 `44923cdeb768a87f4934a6600f55ebe687fcd20d0b253090f52f99226e9eab85`. Elapsed time 165.2 s.
