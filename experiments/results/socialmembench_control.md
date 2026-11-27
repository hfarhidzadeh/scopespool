# SocialMemBench loader control

**Passed**.

- Evidence keys equal the raw turn IDs: 1,979 of 1,979 (1.000) anchors
- Key names a turn containing the excerpt verbatim: 1,979 of 1,979 (1.000)
- Anchor speaker and session agree with the turn: 1,976 of 1,976 (1.000) (three known disagreements excluded)
- Canary returns exactly the evidence turns: 1,031 of 1,031 (1.000) questions
- Unplanted token hits: 0
- Questions failing any part: 0

Criterion: Every anchor: loader key equals the raw turn_id and names a turn containing the excerpt verbatim; speaker and session agree except the three known anchors. Every question: the token-only lexical search returns exactly the loader's evidence keys. An unplanted token returns zero results.

| Network | Turns | Questions | Anchors | Key = turn ID | Excerpt verbatim | Canary | Unplanted |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| grp_0d1e2f3a | 50 | 6 | 12 | 12 | 12 | 6 | 0 |
| grp_1a2b3c4d | 101 | 12 | 23 | 23 | 23 | 12 | 0 |
| grp_2b3c4d5e | 67 | 10 | 16 | 16 | 16 | 10 | 0 |
| grp_3c4d5e6f | 61 | 8 | 14 | 14 | 14 | 8 | 0 |
| grp_4d5e6f7a | 53 | 9 | 23 | 23 | 23 | 9 | 0 |
| grp_5e6f7a8b | 50 | 8 | 17 | 17 | 17 | 8 | 0 |
| grp_6f7a8b9c | 50 | 7 | 12 | 12 | 12 | 7 | 0 |
| grp_7a8b9c0d | 50 | 5 | 9 | 9 | 9 | 5 | 0 |
| grp_8b9c0d1e | 50 | 6 | 10 | 10 | 10 | 6 | 0 |
| grp_9c0d1e2f | 50 | 6 | 12 | 12 | 12 | 6 | 0 |
| grp_a0b1c2d3 | 160 | 24 | 41 | 41 | 41 | 24 | 0 |
| grp_a1b2c3d4 | 188 | 28 | 53 | 53 | 53 | 28 | 0 |
| grp_a3b4c5d6 | 122 | 18 | 27 | 27 | 27 | 18 | 0 |
| grp_a4b5c6d7 | 250 | 41 | 71 | 71 | 71 | 41 | 0 |
| grp_a5b6c7d8 | 255 | 34 | 63 | 63 | 63 | 34 | 0 |
| grp_a6b7c8d9 | 290 | 64 | 143 | 143 | 143 | 64 | 0 |
| grp_a9b0c1d2 | 186 | 19 | 44 | 44 | 44 | 19 | 0 |
| grp_b0c1d2e3 | 168 | 28 | 49 | 49 | 49 | 28 | 0 |
| grp_b1c2d3e4 | 300 | 32 | 60 | 60 | 60 | 32 | 0 |
| grp_b2c3d4e5 | 160 | 13 | 31 | 31 | 31 | 13 | 0 |
| grp_b6c7d8e9 | 290 | 42 | 62 | 62 | 62 | 42 | 0 |
| grp_b8c9dae0 | 268 | 40 | 81 | 81 | 81 | 40 | 0 |
| grp_c1d2e3f4 | 160 | 25 | 43 | 43 | 43 | 25 | 0 |
| grp_c1d2e3f7 | 254 | 48 | 78 | 78 | 78 | 48 | 0 |
| grp_c2d3e4f5 | 190 | 27 | 65 | 65 | 65 | 27 | 0 |
| grp_c3d4e5f6 | 160 | 13 | 30 | 30 | 30 | 13 | 0 |
| grp_c6d7e8f9 | 189 | 17 | 33 | 33 | 33 | 17 | 0 |
| grp_d2e3f4a5 | 180 | 24 | 45 | 45 | 45 | 24 | 0 |
| grp_d3e4f5a6 | 257 | 52 | 84 | 84 | 84 | 52 | 0 |
| grp_d4e5f6a7 | 170 | 18 | 36 | 36 | 36 | 18 | 0 |
| grp_d7e8f9a0 | 194 | 19 | 37 | 37 | 37 | 19 | 0 |
| grp_dba9214c | 160 | 27 | 48 | 48 | 48 | 27 | 0 |
| grp_e3f4a5b6 | 182 | 30 | 58 | 58 | 58 | 30 | 0 |
| grp_e5f6a7b8 | 200 | 17 | 35 | 35 | 35 | 17 | 0 |
| grp_e6f7a8b9 | 169 | 16 | 29 | 29 | 29 | 16 | 0 |
| grp_e7f8a9b1 | 289 | 57 | 172 | 172 | 172 | 57 | 0 |
| grp_e8f9a0b1 | 200 | 28 | 48 | 48 | 48 | 28 | 0 |
| grp_f1a2b3c5 | 302 | 54 | 96 | 96 | 96 | 54 | 0 |
| grp_f2e3d4c5 | 129 | 18 | 28 | 28 | 28 | 18 | 0 |
| grp_f4a5b6c7 | 178 | 24 | 34 | 34 | 34 | 24 | 0 |
| grp_f6g7h8i9 | 200 | 16 | 35 | 35 | 35 | 16 | 0 |
| grp_f7a8b9c0 | 173 | 19 | 34 | 34 | 34 | 19 | 0 |
| grp_f9a0b1c2 | 200 | 22 | 38 | 38 | 38 | 22 | 0 |

Dataset qunlexie/SocialMemBench (CC-BY-4.0) at revision `efd0a5f526871437943d385a59ea93339ef61438`; input and code SHA-256 in the JSON report. Python 3.9.6.
