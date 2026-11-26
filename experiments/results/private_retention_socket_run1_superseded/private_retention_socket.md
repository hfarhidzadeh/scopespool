# Private retention over the Unix socket

4/4 matched pairs passed. Each pair checks completed requests, exact search, observer and prune outputs, and the returned private memory IDs and counts for every reader after shared pruning.

The production client opens a new local socket for each call to a separate threaded ScopeSpool server process. Timings include connection setup, signed-token verification, JSON, store work and the decoded response. The harness seeds independent copies of a synthetic WAL database, starts the server, issues tokens and applies the administrative prune outside the timed client calls.

Each arm runs 4 warmup and 24 serial searches, 12 concurrent searches per reader and 6 personal-list calls per reader. Search limit 5. The peer, joint audience and disjoint viewer are queried before the workload, after the reads, and after pruning. Arm order alternates by repetition.

| Memories / readers | Pair | Mode | All requests OK / attempted | Serial p95 (ms) | Concurrent p95 (ms) | Successful concurrent calls/s | Personal list p95 (ms) | Retained per reader |
| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | --- |
| 256 / 2 | 1 | silent | 79/79 | 7.82 | 13.83 | 158.10 | 2.37 | 0, 0 |
| 256 / 2 | 1 | private | 79/79 | 21.32 | 27.85 | 105.39 | 20.37 | 105, 50 |
| 256 / 2 | 2 | private | 79/79 | 18.35 | 31.16 | 86.06 | 14.97 | 99, 54 |
| 256 / 2 | 2 | silent | 79/79 | 12.07 | 129.20 | 63.25 | 2.12 | 0, 0 |
| 1,024 / 4 | 1 | silent | 115/115 | 163.13 | 234.04 | 22.23 | 1.82 | 0, 0, 0, 0 |
| 1,024 / 4 | 1 | private | 115/115 | 32.74 | 196.39 | 23.30 | 9.48 | 99, 53, 53, 50 |
| 1,024 / 4 | 2 | private | 115/115 | 30.34 | 273.74 | 21.45 | 9.63 | 103, 49, 49, 51 |
| 1,024 / 4 | 2 | silent | 115/115 | 21.07 | 384.31 | 21.79 | 2.65 | 0, 0, 0, 0 |

Latency percentiles summarize successful requests. Concurrent throughput divides successful searches by total wall time, including failed calls and worker startup. The JSON records client-visible errors and their latency separately. Results describe this local lexical fixture and runtime. The workload has no latency threshold.

Python 3.9.6, SQLite 3.39.5, macOS-13.7.8-x86_64-i386-64bit. Store SHA-256 `4e49c69ef178138f7ff219aef817289cfcdfa0dfc174b1ce52682b74d4f6aa8c`. Server SHA-256 `dda5a98d6a374ac1dfc3c14eac930a52fd8fb0f824469391a49fe3c8bdccf0fd`.

Reproduce with `python3 -I experiments/private_retention_socket.py --output /tmp/private_retention_socket`.
