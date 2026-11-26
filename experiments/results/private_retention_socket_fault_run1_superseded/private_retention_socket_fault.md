# Private retention over the Unix socket

Sizes (memories/readers) 256/2; 2 paired repetitions; injected fault: wrong-member.

**Acceptance gate: fail (c, d failed; first failing: 256 memories, pair 1).** Pre-registered in the script's docstring; each criterion must hold in every pair.

| Criterion | Pairs held |
| --- | ---: |
| (a) every request and concurrent prune preview completed in both arms | 2/2 |
| (b) identical searches, observer probes, previews and applied prune between arms | 2/2 |
| (c) each private reader's list equals its own archived results; silent lists empty | 0/2 |
| (d) peer and outsider lists empty; private rows only for readers who searched privately | 0/2 |

Fault validation: criterion (d) failed in 2/2 pairs; detected.

The production client opens a new local socket for each call to a separate threaded ScopeSpool server process. Timings include connection setup, signed-token verification, JSON, store work and the decoded response. The harness seeds independent copies of a synthetic WAL database, starts the server, issues tokens, runs prune previews through the trusted local store alongside the concurrent socket reads, and applies the administrative prune outside the timed client calls.

Each arm runs 4 warmup and 24 serial searches, 12 concurrent searches per reader with 2 prune previews, and 6 personal-list calls per reader. Search limit 5. The peer, joint audience and disjoint viewer are queried before the workload, after the reads, and after pruning. Arm order alternates by repetition.

| Memories / readers | Pair | Mode | All requests OK / attempted | Serial p95 (ms) | Concurrent p95 (ms) | Successful concurrent calls/s | Preview p95 (ms) | Personal list p95 (ms) | Retained per reader |
| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 256 / 2 | 1 | silent | 81/81 | 14.91 | 32.84 | 79.97 | 30.66 | 7.21 | 0, 0 |
| 256 / 2 | 1 | private | 81/81 | 28.46 | 38.28 | 64.89 | 25.19 | 7.55 | 0, 0 |
| 256 / 2 | 2 | private | 81/81 | 27.56 | 46.29 | 56.73 | 52.09 | 7.25 | 0, 0 |
| 256 / 2 | 2 | silent | 81/81 | 16.24 | 30.23 | 86.24 | 26.00 | 9.76 | 0, 0 |

Latency percentiles summarize successful requests. Concurrent throughput divides successful searches by total wall time, including failed calls and worker startup. The JSON records client-visible errors and their latency separately. Results describe this local lexical fixture and runtime; latency and throughput are not gated.

Python 3.9.6, SQLite 3.39.5, macOS-13.7.8-x86_64-i386-64bit. Store SHA-256 `f88e788c1ef1c71ed3f5bbb0e12d7e9e57ffb5f37f0759225dc5dd835786c00d`. Server SHA-256 `dda5a98d6a374ac1dfc3c14eac930a52fd8fb0f824469391a49fe3c8bdccf0fd`. Elapsed time 12.2 s.
