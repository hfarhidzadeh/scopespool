# SocialMemBench retrieval

SocialMemBench is a synthetic, LLM-generated benchmark of WhatsApp-style group
chats: 43 social networks of 4–30 members, 348 sessions, 7,355 turns and 1,031
questions in nine categories (attribution, group decisions, theory of mind,
norms versus individuals, temporal change, departed members and others). Each
question cites evidence anchors: a turn ID, the session and speaker, and a
verbatim excerpt of the turn. [Owolabi, SocialMemBench v2, §3.4](https://arxiv.org/html/2605.17789v2#S3.SS4) ·
[Dataset card](https://huggingface.co/datasets/qunlexie/SocialMemBench)

ScopeSpool loads each network as one evaluation set. The anchors make it a
second loader check alongside EverMemBench, with much shorter histories
(about 171 turns per network).

## Source, licence and pinned files

- Dataset: `qunlexie/SocialMemBench` on Hugging Face, public and not gated.
- Licence: **CC BY 4.0** (card metadata, card text and the paper's footnote
  agree). Research use is allowed with attribution; cite the paper (EACL 2027).
- Pinned revision: `efd0a5f526871437943d385a59ea93339ef61438` (2026-11-18,
  "Cite the EACL 2027 paper"). Earlier commits: `3c638a0` (row-key note),
  `4a4e2f1` (camera-ready release), `68593323` (initial).
  [Pinned tree](https://huggingface.co/datasets/qunlexie/SocialMemBench/tree/efd0a5f526871437943d385a59ea93339ef61438)

The top-level files and their SHA-256 values are listed below. Each value
equals the Hugging Face LFS object ID. The copies under `*/data/` are
byte-identical.

| File | Bytes | Rows | SHA-256 |
| --- | ---: | ---: | --- |
| `conversations.parquet` | 756,453 | 7,355 | `f9ed5d10501cd8a46ca09bb914866ae3069136c259d99ee24dd175e30c90c88d` |
| `qa.parquet` | 895,444 | 1,031 | `98990f88a25df0d9a017488d39ca50e76f432b6554c67b2beafa5f9421ee3f5e` |
| `networks.parquet` | 138,771 | 43 | `e85e7bfd5fd61bf4d5cbd7ad49b3c57a945198480e6c2dba46499fba1ced1a57` |
| `personas.parquet` | 338,600 | 430 | `723d941291a0c5ce30c9892670cd7571796d6e0b0b6487212009c3a1ed026a62` |
| `README.md` (card) | 8,955 | | `a16383cd56109587c3d38ac186132e6dc9f0307bd9e15be3f4059a6c11374ab1` |
| `croissant.json` | 34,355 | | `d852e9017dc0fde7e6d543a7d2ffa23c10a3fc3d1de69fb459676fca0b9bfaa6` |

Keep the data outside the repository:

```bash
rev=efd0a5f526871437943d385a59ea93339ef61438
mkdir /path/to/SocialMemBench && cd /path/to/SocialMemBench
for f in conversations.parquet qa.parquet; do
  curl -fL -o "$f" "https://huggingface.co/datasets/qunlexie/SocialMemBench/resolve/$rev/$f"
done
```

## Card and paper versus the files

The checks were made on the pinned files. The counts agree with the card and
with the paper's Tables 3 and 6:

- 43 networks: 19 small (4–6 members), 14 medium (8–10) and 10 large (15–30).
- 430 personas and 660 relationship edges.
- 348 sessions and 7,355 turns, 21.1 turns per session.
- 1,031 questions. By type, Q1–Q9: 249, 81, 22, 80, 92, 54, 181, 262, 10.
- The tier rows of Table 3 match.
- Four `qa_id` values recur in two networks each, as the card says.
- The blind-critic phase 1 mean is 0.952.
- Every anchor's turn ID resolves within its network. Every excerpt is an
  exact substring of its turn (1,979 of 1,979).

Mismatches and things the card does not say:

1. **Column names and types differ from the card.** Every nested column is a
   JSON string with a `_json` suffix: `evidence_anchors_json`,
   `options_json`, `temporal_anchors_json`, `active_participants_json`,
   `edges_json`, `group_norms_json` and `metadata_json`.
   - Card-only columns: `query_type_label` in `qa`, and `seed` and `personas`
     in `networks`.
   - File-only columns: `corpus_start_date` and `timestamp_label` in
     `conversations`, `generation_seed` and `metadata_json` in `qa`, and
     `n_personas` in `networks`. Personas live in a separate fourth config,
     `personas`. The card says "three configurations".
2. **`turn_id` suffixes are not indices.** For 6,036 turns the `_tNNN` suffix
   is `message_index - 1`. For 1,315 it equals `message_index`, and for 4 it
   is `message_index - 2`. One ID has a letter (`grp_2b3c4d5e_s04_t009b`).
   Use turn IDs as opaque keys.
3. **Three anchors disagree with their turn.** Two name another speaker: in
   network `grp_d3e4f5a6`, `Q8_8a371f10` (turn `…_s02_t009`) and
   `Q8_0e6c7026` (turn `…_s10_t023`) give Quinn and Nico for turns by Pat.
   One names the wrong session: `grp_e3f4a5b6` `Q8_5fd3bd95` gives session 1
   for turn `…_s04_t003`.
4. **Two anchors carry an undocumented `additional_excerpts` field.** It is a
   list of strings in one and a list of objects in the other. Another 49
   anchors carry an undocumented `turn_index`, which always equals the turn's
   `message_index`.
5. **Display names do not always match the persona.** Joined on
   (`network_id`, `persona_id`), 71 turns differ:
   - 31 differ only by an accent (`Tomás`/`Tomas`).
   - In network `grp_a1b2c3d4`, 40 turns rotate the names of three personas.
     The persona ID and the display name then point to different people,
     which matters for attribution questions.
   - Eight `persona_id`s recur across networks, so a persona ID is unique
     only within its network.
6. **Some fields differ from the card's types and nulls.**
   - The card says `session_gap_days` is null for session 1; it is 0 in all
     868 session-1 rows.
   - `reply_to_turn_id` is never null; 4,393 rows hold an empty string.
   - The card says `active_participants` is filled for medium and large
     groups only; it is filled for every small-group turn too.
   - Multiple-choice `options` is a dict in 184 rows and a list
     (`["A) …", …]`) in 30.
7. **"No QA pair is shipped without grounded evidence anchors"** stands
   against 7 rows with `qc_phase2_grounded = false`. They are kept in the
   released file, and all of their anchors still resolve verbatim.
8. **Excerpt length.** The paper's appendix limits a planted `evidence_span`
   to 200 characters. Of the 1,979 anchor excerpts, 90 are longer (maximum
   296). Those are a different field, so this may not be an error.
9. **Size is stated in tokens.** The paper gives 292,725 GPT-4o-mini tokens
   in total. "About 6,800 tokens per network" is that total divided by 43;
   the paper does not state it. Message text alone is about 3,500 words
   (about 4,700 tokens at four characters per token) per network, ranging
   from 659 to 7,795 words. The rest presumably comes from speaker names,
   timestamps and session headers. This was not checked with the tokenizer.

## Loader

`dynmemory.socialmembench` uses the standard library only.

- `read_parquet` reads flat Parquet files: one level of required or optional
  primitive columns, uncompressed or Snappy, and PLAIN or dictionary pages
  (data page v1 or v2). It raises an error for nested schemas, other codecs
  and other encodings rather than guess. On all four pinned files it matched
  pyarrow 17 on every cell, value and type (149,570 cells).
- `read_release(root, verify=True)` checks each file against its pinned
  SHA-256 before reading.
- `build_networks` and `load_networks(root)` return one evaluation set per
  network, sorted by network ID.
- Each memory is a turn keyed by its `turn_id`. It keeps the speaker display
  name and persona ID, the network (as its channel), the session ID and
  index, the message index, the ISO timestamp, the session date and the
  reply-to turn.
- `related_to` links join consecutive turns within a session.
- Each question keeps its wording, and each distinct anchored turn is one
  required group. `evidence` keeps every anchor's key, excerpt and stated
  speaker and session.
- Tags give the query type, difficulty, answer format, evidence-turn count
  and single- or cross-session. Answers are not copied.
- An anchor whose turn is missing or in another network raises an error, as
  do duplicate turn IDs, positions or question IDs within a network.

```python
from pathlib import Path
from dynmemory.socialmembench import load_networks

networks = load_networks(Path("/path/to/SocialMemBench"))
question = networks[0]["queries"][0]
evidence_turns = question["relevant"]
```

## Verify the loader

`experiments/socialmembench_control.py` fixed its rule in its docstring on
2026-11-27, before it ran on the real data. Achievability was measured first,
independently of the loader, with pyarrow on the full release. Every excerpt
was verbatim in its turn, and only the three anchors in mismatch 3 disagreed
on speaker or session. So the rule requires 1.0, with those three excluded
from the attribution check only:

- **A. Evidence resolution.** For every anchor:
  - the loader's key equals the raw `turn_id`, parsed separately from the
    raw JSON;
  - the key names a loaded turn that contains the excerpt verbatim;
  - the stated speaker and session match that turn.
- **B. Canary.** For each question, the control finds each anchored turn by
  its raw `turn_id` in the raw conversation rows. It appends one unique token
  to that turn in an in-memory store holding the whole network, with no
  links and no embedder, and restores the rows afterwards. The token-only
  lexical search, limited to ten results, must return exactly the loader's
  evidence keys, no more and no fewer. An unplanted token must return
  nothing in every network.

Two faults rewrite the loader's output to simulate a bug, so the rule must
fail:

- `off-by-one` maps every key to the next turn of its session.
- `turn-suffix` resolves turn IDs by parsing the suffix as a zero-based
  index, the shortcut that mismatch 2 rules out.

```bash
results_dir="$(mktemp -d)"
python3 -I experiments/socialmembench_control.py --data /path/to/SocialMemBench \
  --output "$results_dir/socialmembench_control.json"
python3 -I experiments/socialmembench_control.py --data /path/to/SocialMemBench \
  --fault off-by-one --output "$results_dir/socialmembench_control_off-by-one.json"
python3 -I experiments/socialmembench_control.py --data /path/to/SocialMemBench \
  --fault turn-suffix --output "$results_dir/socialmembench_control_turn-suffix.json"
```

Results on 2026-11-27, with Python 3.9.6, store SHA-256 `7f427634…`, loader
`3b3074a1…` and control `da5f9ac0…`
([normal](../experiments/results/socialmembench_control.md),
[`off-by-one`](../experiments/results/socialmembench_control_off-by-one.md),
[`turn-suffix`](../experiments/results/socialmembench_control_turn-suffix.md)):

| Run | Key = turn ID | Excerpt verbatim | Speaker and session | Canary exact | Unplanted hits | Verdict |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| Normal | 1,979 / 1,979 | 1,979 / 1,979 | 1,976 / 1,976 | 1,031 / 1,031 | 0 | Passed |
| `off-by-one` | 0 / 1,979 | 4 / 1,979 | 30 / 1,976 | 0 / 1,031 | 0 | Fault detected |
| `turn-suffix` | 1,700 / 1,979 | 1,701 / 1,979 | 1,699 / 1,976 | 885 / 1,031 | 0 | Fault detected |

Each run took 13–29 seconds. The three known disagreements were seen, and all
three still disagree. The turn-suffix shortcut would silently misplace 279
anchors (14.1%) and corrupt 146 questions (14.2%). The same runs on the
earlier store (`40258276…`) gave identical counts.

The unit tests (`tests/test_socialmembench.py`) use only synthetic rows and
small synthetic Parquet files embedded in the test, written by pyarrow. They
cover:

- Snappy and dictionary data page v1, and uncompressed PLAIN data page v2;
- rejection of nested columns, zstd and non-Parquet files;
- Snappy copies that overlap their own output;
- hash pinning;
- the loader's keys, links and errors;
- the control passing on correct keys and failing under both faults, under
  a missing excerpt, under an unlisted attribution disagreement, and under
  a missing or extra canary witness;
- row restoration after an error.

All 16 tests pass on Python 3.9.6, and on 3.14 with ResourceWarnings as
errors. The tests were also run against seven deliberately broken copies of
the loader and control, and each copy failed at least one test.

## Limits

- **The data is synthetic.** The conversations, questions and quality checks
  come from one generator model family. A single author built the dataset;
  there is no human-written conversation.
- **The control tests the loader, not retrieval.** A token-only canary
  checks that the evidence keys are stored, retrievable and mapped back
  correctly. It says nothing about whether question text ranks the
  evidence. No retrieval experiment has been pre-registered.
- **Some excerpts are weak evidence on their own.**
  - 792 excerpts are the whole message, and some are a single word or emoji.
    For example, the excerpt `in` is a substring of 184 turns of its network.
  - 34 excerpts occur in more than one turn of their network.
  - Any check that searches for excerpt text, rather than resolving turn
    IDs, would be ambiguous for those.
- **Who-said-what is not fully clean.** Mismatches 3 and 5 affect
  attribution questions. The loader keeps both the display name and the
  persona ID so either can be used.
- **Personas, edges and norms are not loaded.** Only conversations and
  questions are.
- **Q9 "departed member" questions reward remembering a member who left.**
  Revocation needs the opposite behaviour.
- **Histories are short.** About 171 turns per network fit in a context
  window, so this benchmark cannot show a benefit of retrieval over full
  context.
