# SocialMemBench loader control

**Fault detected**; injected fault `off-by-one`.

- Evidence keys equal the raw turn IDs: 0 of 1,979 (0.000) anchors
- Key names a turn containing the excerpt verbatim: 4 of 1,979 (0.002)
- Anchor speaker and session agree with the turn: 30 of 1,976 (0.015) (three known disagreements excluded)
- Canary returns exactly the evidence turns: 0 of 1,031 (0.000) questions
- Unplanted token hits: 0
- Questions failing any part: 1,031

Criterion: Every anchor: loader key equals the raw turn_id and names a turn containing the excerpt verbatim; speaker and session agree except the three known anchors. Every question: the token-only lexical search returns exactly the loader's evidence keys. An unplanted token returns zero results.

| Network | Turns | Questions | Anchors | Key = turn ID | Excerpt verbatim | Canary | Unplanted |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| grp_0d1e2f3a | 50 | 6 | 12 | 0 | 0 | 0 | 0 |
| grp_1a2b3c4d | 101 | 12 | 23 | 0 | 0 | 0 | 0 |
| grp_2b3c4d5e | 67 | 10 | 16 | 0 | 0 | 0 | 0 |
| grp_3c4d5e6f | 61 | 8 | 14 | 0 | 0 | 0 | 0 |
| grp_4d5e6f7a | 53 | 9 | 23 | 0 | 0 | 0 | 0 |
| grp_5e6f7a8b | 50 | 8 | 17 | 0 | 0 | 0 | 0 |
| grp_6f7a8b9c | 50 | 7 | 12 | 0 | 0 | 0 | 0 |
| grp_7a8b9c0d | 50 | 5 | 9 | 0 | 0 | 0 | 0 |
| grp_8b9c0d1e | 50 | 6 | 10 | 0 | 0 | 0 | 0 |
| grp_9c0d1e2f | 50 | 6 | 12 | 0 | 0 | 0 | 0 |
| grp_a0b1c2d3 | 160 | 24 | 41 | 0 | 0 | 0 | 0 |
| grp_a1b2c3d4 | 188 | 28 | 53 | 0 | 0 | 0 | 0 |
| grp_a3b4c5d6 | 122 | 18 | 27 | 0 | 0 | 0 | 0 |
| grp_a4b5c6d7 | 250 | 41 | 71 | 0 | 0 | 0 | 0 |
| grp_a5b6c7d8 | 255 | 34 | 63 | 0 | 0 | 0 | 0 |
| grp_a6b7c8d9 | 290 | 64 | 143 | 0 | 2 | 0 | 0 |
| grp_a9b0c1d2 | 186 | 19 | 44 | 0 | 0 | 0 | 0 |
| grp_b0c1d2e3 | 168 | 28 | 49 | 0 | 0 | 0 | 0 |
| grp_b1c2d3e4 | 300 | 32 | 60 | 0 | 0 | 0 | 0 |
| grp_b2c3d4e5 | 160 | 13 | 31 | 0 | 1 | 0 | 0 |
| grp_b6c7d8e9 | 290 | 42 | 62 | 0 | 0 | 0 | 0 |
| grp_b8c9dae0 | 268 | 40 | 81 | 0 | 0 | 0 | 0 |
| grp_c1d2e3f4 | 160 | 25 | 43 | 0 | 0 | 0 | 0 |
| grp_c1d2e3f7 | 254 | 48 | 78 | 0 | 1 | 0 | 0 |
| grp_c2d3e4f5 | 190 | 27 | 65 | 0 | 0 | 0 | 0 |
| grp_c3d4e5f6 | 160 | 13 | 30 | 0 | 0 | 0 | 0 |
| grp_c6d7e8f9 | 189 | 17 | 33 | 0 | 0 | 0 | 0 |
| grp_d2e3f4a5 | 180 | 24 | 45 | 0 | 0 | 0 | 0 |
| grp_d3e4f5a6 | 257 | 52 | 84 | 0 | 0 | 0 | 0 |
| grp_d4e5f6a7 | 170 | 18 | 36 | 0 | 0 | 0 | 0 |
| grp_d7e8f9a0 | 194 | 19 | 37 | 0 | 0 | 0 | 0 |
| grp_dba9214c | 160 | 27 | 48 | 0 | 0 | 0 | 0 |
| grp_e3f4a5b6 | 182 | 30 | 58 | 0 | 0 | 0 | 0 |
| grp_e5f6a7b8 | 200 | 17 | 35 | 0 | 0 | 0 | 0 |
| grp_e6f7a8b9 | 169 | 16 | 29 | 0 | 0 | 0 | 0 |
| grp_e7f8a9b1 | 289 | 57 | 172 | 0 | 0 | 0 | 0 |
| grp_e8f9a0b1 | 200 | 28 | 48 | 0 | 0 | 0 | 0 |
| grp_f1a2b3c5 | 302 | 54 | 96 | 0 | 0 | 0 | 0 |
| grp_f2e3d4c5 | 129 | 18 | 28 | 0 | 0 | 0 | 0 |
| grp_f4a5b6c7 | 178 | 24 | 34 | 0 | 0 | 0 | 0 |
| grp_f6g7h8i9 | 200 | 16 | 35 | 0 | 0 | 0 | 0 |
| grp_f7a8b9c0 | 173 | 19 | 34 | 0 | 0 | 0 | 0 |
| grp_f9a0b1c2 | 200 | 22 | 38 | 0 | 0 | 0 | 0 |

Dataset qunlexie/SocialMemBench (CC-BY-4.0) at revision `efd0a5f526871437943d385a59ea93339ef61438`; input and code SHA-256 in the JSON report. Python 3.9.6.
