# Build log — SUTRANETRA (SIH26151)

Per-prompt progress, metrics, and issue notes for demos, judge Q&A, and interviews.
Agents must append a section after every `prompts/NN-name.md` run (pass or fail-stop).
Chat history is not a substitute for this file.

**Product:** SUTRANETRA — *"The eye that follows the hidden threads."* (*Sutra* = thread/connection · *Netra* = eye/vision)

## Entry template

Copy this block for each prompt:

```
### YYYY-MM-DD — prompts/NN-name.md

- **Status:** complete | blocked | partial
- **Profile:** dev | demo
- **What shipped:** …
- **DoD:** item → pass/fail (quote actual output where relevant)
- **Tests:** list → pass/fail
- **Metrics:** row counts, PR-AUC, findings, etc. (honest numbers)
- **Issues / near-misses:** errors, workarounds, degraded paths, open questions
- **Judge/interview notes:** one-liners that answer “why did you do X?” or “what broke?”
```

---

## Log

### 2026-09-03 — prompts/01-ingest-bootstrap.md

- **Status:** complete
- **Profile:** dev
- **What shipped:** `src/ingest/fetch.py`, `smf_parser.py`, `load.py` (`python -m src.ingest.load --market cannabisroad3`); real HTML fixtures under `tests/fixtures/`; tests `test_smf_parser`, `test_dedupe`, `test_post_provenance`.
- **DoD:**
  - Download `cannabisroad3-forums.tar.xz` (2,211,132 bytes, xz magic) → **pass**; re-fetch leaves mtime unchanged
  - Ingest CLI row counts plausible → **pass** (see Metrics)
  - 5-post manual spot-check vs tar HTML → **pass** (msg 4111 / 1267 / 7594 / 596 / 2636)
  - Dedupe: `msg_id=4111` in all 4 scrape folders, **1** DB row, lineage from `2014-11-25` → **pass**
  - Lineage + sha256(raw_html) on inspected posts → **pass**
  - aliases 1:1 with `(market, alias)`; 5 aliases n/first/last match posts; AngelEyes `is_vendor=1` → **pass**
  - Unparseable `ts` stored as NULL and post kept → **pass** (parser test; live corpus has 0 such rows)
- **Tests:** `tests/test_smf_parser.py` 3 passed; `tests/test_dedupe.py` 1 passed; `tests/test_post_provenance.py` 1 passed (5 passed in 0.28s)
- **Metrics:** pages 2606; posts parsed 18970; posts loaded **4764**; aliases **1524**; page failures 0; skipped no-date 0; ts=NULL 0; vendor aliases 35
- **Issues / near-misses:** Live cannabisroad3 HTML has no unparseable timestamps and no `Today at` on topic 440 — relative-ts and NULL-ts covered by unit tests (one mutated real page). `content_sha256` hashes BeautifulSoup's `str(post_wrapper)`, which is what we store in `raw_html` (DoD hash check is against stored HTML, not the original file substring). Vendor flag is the membergroup `"vendor"` substring heuristic, not a marketplace role API. phpBB parser not built (cannabisroad3 is SMF).
- **Judge/interview notes:** 18970 parsed vs 4764 loaded is the 4-scrape overlap; `INSERT OR REPLACE` in ascending scrape-date order is why msg 4111 keeps the 2014-11-25 member path.

### 2026-09-03 — prompts/00-project-scaffold.md

- **Status:** complete
- **Profile:** dev (schema init only; no pipeline run)
- **What shipped:** Full `src/` package tree (`ingest` … `ui`, `opsec/demo_target/`), `tests/`, `data/raw|db|cache/ct/`, `.gitignore`, `requirements.txt` (core stack only), `config.yaml` (dev/demo profiles), `src/ingest/schema.py`, `README.md`.
- **DoD:**
  - `pip install -r requirements.txt` in fresh `.venv` → **pass** (Python 3.13.9 on this machine; spec targets 3.11+)
  - Schema init creates 7 tables with lineage + `case_id` on `pair_scores` → **pass**
  - Second schema init idempotent → **pass**
  - `config.yaml` dev `neo4j.enabled: false`, demo `neo4j.enabled: true` → **pass**
  - Directory tree + `__init__.py` in every `src/` subpackage → **pass**
  - `data/`, `.venv`, `__pycache__` gitignored → **pass** (`data/db/attrib.sqlite` not tracked)
- **Tests:** none required this prompt (`tests/__init__.py` only)
- **Metrics:** 7 tables; `posts` has 19 columns including `raw_html` + 4 lineage fields; `pair_scores` has `case_id` in PK
- **Issues / near-misses:** Added `pyyaml>=6.0` to `requirements.txt` (needed by schema CLI; not listed explicitly in SPEC §20 but required for `config.yaml`). Dev machine used Python 3.13.9 instead of 3.11 — install succeeded; team should still standardize on 3.11 per SPEC if wheel issues appear elsewhere.
- **Judge/interview notes:** Scaffold separates corpus tables from case-scoped results from day one — later prompts don't retrofit investigation semantics.

### 2026-09-03 — brand: SUTRANETRA (not a build prompt)

- **Status:** complete
- **What shipped:** Product name **SUTRANETRA** + tagline + etymology across `SPEC.md`, `AGENTS.md`, `CLAUDE.md`, Prompt 00 README requirement, demo open, validation/build-log headers. Shipped repo tree label `sutranetra/`; this build-kit folder may remain `darkattrib-buildkit`.
- **Judge/interview notes:** Name is Indian-rooted and maps to the product metaphor — following hidden threads (correlation/attribution) with an investigator's eye (Evidence Trail).
- **Issues / near-misses:** none.

### 2026-09-03 — plan: lineage + cases + Evidence Trail (not a build prompt)

- **Status:** complete (plan/prompt sync)
- **What shipped:** `SPEC.md` §6.1 source lineage, §6.2 cases, §15 Evidence Trail tab + `explain/trail.py`; demo §19; tests §18 (`test_post_provenance`, `test_cases`, `test_evidence_trail`). Prompts 00, 01, 02, 07, 08, 09, 10, 11, 13, 15 updated. `AGENTS.md` / `CLAUDE.md` correctness + cut-order updated.
- **Design notes:** Corpus (`posts`/`aliases`/`evidence`) shared; results (`pair_scores`/`clusters`/`opsec_findings`) case-scoped. `content_sha256` hashes UTF-8 `raw_html`. Trail never fabricates OpSec/CT steps.
- **Judge/interview notes:** Case card + Evidence Trail + archive-member lineage is the answer to "how / where / can you reproduce it?"
- **Issues / near-misses:** Prior schema omitted `raw_html` despite evidence extractors needing it — fixed in §6 schema as part of this pass.

### 2026-09-03 — plan framing update (not a build prompt)

- **Status:** complete
- **What shipped:** Formalized three-layer stack in `SPEC.md` §1/§3/§14 and synced `AGENTS.md` / `CLAUDE.md` / `docs/VALIDATION-AND-NOVELTY.md`.
- **Stack:** Correlation → Attribution → Evidence / Investigation.
- **Judge/interview notes:** Third layer is why-believe / what-observed / what-next — turns a calibrated score into an interrogable case file without changing the deterministic scoring path.
- **Issues / near-misses:** none — framing only; no code change.

### 2026-09-03 — prompts/03-evidence-extraction.md

- **Status:** complete (dev; full-corpus extract after Prompt 02 freeze)
- **Profile:** dev
- **What shipped:** `src/evidence/{pgp,crypto_addr,onion,extract,score,htmltext}.py`; CLI `python -m src.evidence.extract`. Contacts taken from stripped `body` so forum chrome is not an onion hit on every post. PGP from unescaped HTML. Invalid IPv6 URLs skipped. Fallback fingerprints must be 8/16/40 hex; `NONE` dropped. Obfuscated email requires `[at]`/`[dot]`, not bare `@` (that was turning `Thanks @copycat. This` into a fake address).
- **DoD:**
  - evidence populated, kinds present: **pgp_fpr, btc, onion, clearnet, email**. **xmr: none** in this corpus.
  - Counts (912,511 posts scanned, 0 extract failures, ~169s): pgp_fpr **10,043**; btc **2,646**; onion **45,381**; clearnet **66,499**; email **3,764**; total **128,333**
  - 10-row spot-check: PGP (Trappy `74D05196…` etc.) and BTC (1JoLLy5…, 1CatnMd3…, checksum-valid) genuine. Onion samples are vendor/market links in post text. Email samples after filter are real (riseup/safe-mail/tightmail). Clearnet: youtube, blockchain.info, rollitup.org genuine; leftover noise still possible on odd TLDs (`mt.gox` is a real historical domain).
  - Multi-alias shared PGP: `D870C6ACCC6E46B0E0C73955B8F1D88EBBF7433B` on **75** aliases. Shared BTC: `1Hq6xxFFEFdzuQHtrx8GPQf7NGE6g287oX` on **16** aliases.
  - S_hard one PGP: **0.875**; empty: **0**
- **Tests:** `test_crypto_addr.py` + `test_pgp.py` + extract/clearnet extras → **10 passed in 0.15s**
- **PGP rate sanity:** CR3 **16** posts with PGP / 4,764 posts. Spec's 23/654 was **pages**, not posts — same order, not 100× off.
- **Judge/interview notes:** Regex-only BTC is the trap; the unit test rejects the MD5 false positive. Shared PGP across 75 aliases includes likely quoted keys / copy-paste, not 75 secret identities — fusion still needs stylometry. Onion counts are dominated by `silkroadvb5piz3r.onion` mentions in SR1 bodies.

### 2026-09-04 — Prompt 02 market cut (throughput)

- **Status:** decision recorded; Silk Road 1 ingest still running
- **Profile:** dev
- **Choice:** ingest **cannabisroad3 + nucleus + silkroad1 + silkroad2 + thehub**. Skip **agora** and **evolution** for this pass.
- **Why:** measured ~14 pages/sec. Spec §22: skip a market rather than block — five is plenty. SR2 = SR1 migration cases; TheHub = highest cross-market overlap for Prompt 04 labels. Agora/Evolution are extra volume/time overlap, not a unique signal.
- **Skip reasons (Prompt 02 DoD):**
  - `agora`: deferred — throughput; overlap already covered by SR2 + TheHub
  - `evolution`: deferred — same; lowest unique signal per hour
- **1M-post risk:** Nucleus was 609k parsed → **64,165 unique**. Unique << parsed because of re-scrapes. Five markets may land under 1M unique rows. If that happens, add Agora next (volume), not Evolution. Do not pretend we hit 1M.
- **Not doing tonight:** do not start Agora/Evolution after SR1. Next: SR2, then TheHub. Archives stay on disk.

### 2026-09-04 — Silk Road 1 stopped after first scrape

- **Status:** SR1 ingest halted on purpose after ~10h / ~168k pages
- **Decision:** first snapshot is enough. DB had **711,202** unique SR1 posts, all `scrape_date=2013-11-03`, **35,649** aliases, **0** null lineage. Remaining pages were later overlapping scrapes (newest-wins), not a new market.
- **Corpus after stop:** cannabisroad3 4,764 + nucleus 64,165 + silkroad1 711,202 = **780,131** posts. Next: silkroad2, then thehub. Agora/evolution still skipped.
- **Judge/interview notes:** SR1 is the 2013-11-03 snapshot only; we did not apply later dumps because of ingest time. Rows are complete and lined.

### 2026-09-04 — Silk Road 2 stopped; The Hub started

- **Status:** SR2 halted after ~5h / 10k pages. TheHub ingest started.
- **SR2 kept:** **112,661** unique posts, **5,986** aliases, scrape dates 2013-12-27 / 2014-01-07 / 2014-01-11, **0** null lineage. Parsed copies were ~219k — remaining work is slow re-scrapes (~1.2 pages/sec).
- **Corpus after stop:** CR3 4,764 + nucleus 64,165 + SR1 711,202 + SR2 112,661 = **892,792** posts, 4 markets. Need TheHub for the fifth market and likely to clear 1M unique.
- **Skip still:** agora, evolution (throughput).

### 2026-09-04 — The Hub stopped; five-market corpus frozen

- **Status:** TheHub halted after ~3h / 8k pages. No further market ingest this pass.
- **TheHub kept:** **19,719** unique posts, **1,674** aliases, scrapes Jan–Apr 2014, **0** null lineage. Unique growth had stalled (~+3k unique while copies doubled) — remaining pages are re-scrapes.
- **Final corpus:** **912,511** posts, **49,357** aliases, **5 markets**. **1,643** aliases appear on 2+ markets (Prompt 04 label source).
- **1M bar:** **not met** (912,511). Honest shortfall ~87k. Chasing it via more TheHub hours would not get there; Agora would. Deferred with the existing skip reason.
- **Skipped:** agora, evolution (throughput / overlap already covered).

### 2026-09-04 — prompts/02-ingest-scale.md

- **Status:** complete with honest shortfall (5 markets, 912,511 posts ≠ 1M)
- **Profile:** dev
- **What shipped:** phpBB/PunBB fallback (`src/ingest/phpbb_parser.py`) triggered by nucleus; SMF path used for CR3/SR1/SR2/TheHub; multi-market load + progress; `config.yaml` primary five + skipped_markets.
- **DoD:**
  - ≥1M posts / ≥5 markets → **fail the 1M number, pass 5 markets.** Actual: **912,511** posts, markets `cannabisroad3, nucleus, silkroad1, silkroad2, thehub`. Short by **87,489**. Cause: unique << parsed (re-scrapes); Agora/Evolution skipped for throughput; SR1/SR2/TheHub stopped after unique growth flattened. Agora would close the gap; more Hub hours would not.
  - null lineage → **0** (queried)
  - Per-market (parser / posts / aliases / scrape range / sample lineage):
    - cannabisroad3 SMF 4,764 / 1,524 / 2014-11-23..25 / `cannabisroad3-forums.tar.xz` / 2014-11-25 / `.../index.php?topic=2.0`
    - nucleus phpBB 64,165 / 4,524 / 2014-11-21..2015-07-05 / `nucleus-forums.tar.xz` / 2015-04-26 / `.../viewtopic.php?id=2`
    - silkroad1 SMF 711,202 / 35,649 / 2013-11-03 snapshot / `silkroad1-forums.tar.xz` / 2013-11-03 / `.../index.php?topic=3.msg894`
    - silkroad2 SMF 112,661 / 5,986 / 2013-12-27..2014-01-11 / `silkroad2-forums.tar.xz` / 2014-01-07 / `.../index.php?topic=3.0;all`
    - thehub SMF 19,719 / 1,674 / 2014-01-26..2014-04-21 / `thehub-forums.tar.xz` / 2014-04-21 / `.../index.php?topic=2.0`
  - Skipped: **agora** — throughput; volume/overlap already covered by SR2+TheHub. **evolution** — same; lowest unique signal per hour. Archives remain on disk.
  - Re-run same market: `test_multi_market_load.py` totals stable; fetch skips valid xz already on disk.
  - phpBB 5-post live spot-check (nucleus msg 2–6: sniffsniff, twister, heydude, vrc, vrc) — lineage + sha256 + raw_html populated.
- **Tests:** `test_smf_parser.py` (incl. silkroad1 fixture), `test_phpbb_parser.py`, `test_dedupe.py`, `test_post_provenance.py`, `test_multi_market_load.py` → **8 passed in 0.42s**
- **Aliases table:** 49,357 rows. **1,643** aliases appear on 2+ markets.
- **Judge/interview notes:** We did not hit 1M unique posts. We hit 5 markets and the signals that matter (SR1→SR2 migration corpus, TheHub overlap). Do not say 1M on stage.

### 2026-09-04 — prompts/04-ground-truth-labels.md

- **Status:** complete
- **Profile:** dev
- **What shipped:** `src/fusion/labels.py` → staging table `label_pairs` (not `pair_scores`; no case yet). CLI `python -m src.fusion.labels`. §11.3 caveat in the module docstring. Blind-protocol note: this module does not vectorize; Prompts 05–06 must redact alias strings.
- **DoD:**
  - Positives (same username, ≥2 markets): **2,075**. Spans: SR1|SR2 1027, SR2|TheHub 338, SR1|TheHub 212, nucleus|SR1 169, nucleus|SR2 110, CR3|SR1 65, nucleus|TheHub 57, CR3|TheHub 38, CR3|SR2 32, CR3|nucleus 27.
  - Random cross-market negatives: **2,075**. Hard negatives (same market, shared thread_id, no shared evidence): **2,075**.
  - 5 positives inspected: `007`, `03welle`, `0woorrdd` on SR1+SR2; `0x00` SR1+TheHub; `1200mics` SR2+TheHub — same alias string on both markets with post counts.
  - 3 hard negs: silkroad1 `590nm`/`midlandsmafia`, `flow378`/`tropicalis`, `CT`/`phrost70` — co_threads=1, shared_ev=0.
  - Positives 2075 ≫ 30; TheHub already ingested; **temporal-split fallback not used**.
- **Tests:** `tests/test_labels.py` **3 passed** (Nightcrawler fixture `label=1`; hard-neg never shares evidence; corpus `Jack N Hoff` SR1+SR2 in `label_pairs`).
- **Judge/interview notes:** Same handle is a heuristic, not identity. No planted positives. `Jack N Hoff` is a real recurring handle.

### 2026-09-04 — prompts/05-stylometry-char-ngram-blocking.md

- **Status:** complete
- **Profile:** dev
- **What shipped:** `src/stylometry/hygiene.py`, `redact.py`, `char_ngram.py`, `blocking.py`. CLI `python -m src.stylometry.char_ngram`. Staging table `char_candidates` (neighbors ∪ eval only). `config.yaml` `blocking_svd_dims: 256`.
- **DoD:**
  - Vocab size **200,000** (hit `max_features` cap) → **pass**
  - Sanity S_char: `Jack N Hoff` SR1/SR2 **0.516**; random_neg `Mwhite`/`Skittles4` **0.065** (same direction as mean pos 0.183 vs mean random_neg 0.082) → **pass**
  - Candidate union **18,347,050** vs full **1,218,032,046** pairs (49,357 aliases). Persisted TF-IDF scores: **2,257,292** (2,251,456 neighbor + 6,225 eval). Reduction vs N² is ~66× for the union, ~540× for neighbours-only.
  - Blocking recall **forced = 1.0** (2075/2075). **Neighbors-only (honest) = 0.155** (321/2075). Do not quote 1.0 on stage without the 0.155.
  - Hygiene: cannabisroad3 `msg_id=4130` — quoted “epi pen” / “Whole Foods mango bin” absent; own line “sister has the same problem with mangos” kept; signature email stripped → **pass**
- **Tests:** `test_redaction.py` 2 passed; `test_hygiene.py` 1 passed; `test_blocking.py` 1 passed (**4 passed**).
- **Issues / near-misses:** Shared forum onions (`silkroadvb5piz3r.onion` on 4,224 aliases) make hard-evidence combinations ~16M extra pairs. First persist of that union onto iCloud SQLite stalled; those clique pairs are counted in the union/recall stats but **not** stored. `S_char` in `char_candidates` is full TF-IDF cosine for neighbors ∪ eval. Honest blocking recall is low because same-username cross-market positives are often not stylometric near-duplicates — that is why force-include exists.
- **Judge/interview notes:** Char n-grams are the topic-robust channel. Blind protocol is `redact.py` (handle + separators + leet + digit suffix), not dropping the label column. Report both blocking recalls.

### 2026-09-05 — prompts/06-stylometry-embeddings-temporal.md

- **Status:** complete
- **Profile:** dev
- **What shipped:** `src/stylometry/embed.py` (MiniLM CPU, batch 64, cap 200 posts/alias, Prompt 05 hygiene+redact), `src/temporal/activity.py` (hour/dow hists, JS S_time, weak TZ). Scores in `pair_channel_scores`; TZ in `alias_activity`. CLIs: `python -m src.stylometry.embed`, `python -m src.temporal.activity`.
- **DoD:**
  - Embed runtime **7881 s (~2.2 h)** for **48,848** aliases / **758,314** capped posts; **2,257,292** candidate pairs scored. **2,231,208** rows have non-NULL `s_embed` (empty-doc aliases stay NULL).
  - Prompt 05 pair `Jack N Hoff` SR1/SR2: **s_char=0.516, s_embed=0.876**. Random_neg `Mwhite`/`Skittles4`: **s_char=0.065, s_embed=0.242**. Constructed cannabis casual-vs-formal pair (unit test): MiniLM topic score **>** char style score by ≥0.15 with topic >0.45 → **pass** (channels diverge). Naive corpus `s_embed≈1 / s_char≈0` hits are thin/garbled aliases (e.g. `martin420` n_posts=2) — do not use those as the demo pair.
  - `S_time`: eligible aliases **10,027**; NULL floor **38,981**. Pair scores: **399,995** numeric, **1,857,297** NULL. Samples: AfriKanSun/SmileCrew **0.421** (n_ts 93/58); AfriKanSun/microbabe **0.437**; AfriKanSun/mushitup **0.466**. NULL path: `0shit`@cannabisroad3 n_ts=1.
  - TZ (weak, not a location claim): `ohluckyman`@silkroad1 R=1.00 on 23 ts, UTC mass ~11h → evening-peak hypothesis UTC+9, East Asia/Australia band. `Kublai_Khan`@silkroad2 R=1.00 on 23 ts, UTC mass ~5h → UTC−9, Americas Pacific/Alaska band.
- **Tests:** `test_temporal.py` 3 passed; `test_embed_vs_char.py` 1 passed (MiniLM). Combined with Prompt 05 tests 8 passed when MiniLM is run in a separate pytest process (one in-process suite hit a torch segfault after the long embed job).
- **Issues / near-misses:** CPU MiniLM at batch 64 was ~100 posts/s. `S_embed=1.0` with `s_char=0` on 1–2 post aliases is vector collapse, not a two-channel success. `S_time=1.0` on ORDER BY DESC is identical hour histograms, not a demo highlight — use mid-range pairs. Missing `S_time` is SQL NULL, never 0. Fusion (Prompt 07) must impute + `time_missing`.
- **Judge/interview notes:** `S_embed` is topic/domain proximity, never style. Char n-grams are the style channel. Timezone is an evening-peak UTC-offset *hypothesis* with concentration R as confidence.

### 2026-09-05 — prompts/07-fusion-model.md

- **Status:** complete
- **Profile:** dev (learned LogisticRegression, **not** heuristic)
- **What shipped:** `src/pipeline/case.py`; `src/fusion/features.py`, `model.py`, `evaluate.py`. CLI `python -m src.fusion.model --case-id CASE-2026-001`. Plots `docs/eval/pr_curve.png`, `docs/eval/confusion_matrix.png`. Model file `data/models/fusion-v1.joblib` (gitignored).
- **DoD:**
  - Case **CASE-2026-001**: snapshot `n_posts=912511, n_aliases=49357`, five markets; `config_hash=9401b484…`; `model_version=fusion-v1@113d4e19`; `threshold=0.83`; `status=complete`.
  - Alias-disjoint split **True** (handle-grouped): 5615 train alias_ids ∩ 1727 test = ∅. Train 3454 pairs (1404 pos); test 1049 (671 pos). Mixed-handle pairs dropped.
  - Coefficients: s_time **2.03**, s_hard **1.68**, s_embed **1.12**, time_missing **1.05**, s_char **0.34**, log1p_n_shared_hard **−0.32**, intercept **−2.16**. Hard evidence is large-positive as designed; log1p is negative from collinearity with saturating S_hard. time_missing>0 is a labelled-set quirk (many positives are timestamp-sparse) — do not sell it as “missing time means same person.”
  - Held-out @0.83: precision **1.0**, recall **0.0149** (10/671), F1 **0.029**, **PR-AUC 0.768**. Headline is PR-AUC, not accuracy, not this recall. Threshold 0.83 is conservative on this split.
  - PNGs exist (PR 720×600, confusion 540×480).
  - `pair_scores`: **2,257,292** rows all `case_id=CASE-2026-001`. Second case **CASE-2026-002** threshold **0.70**, 25 rows; case 001 unchanged.
  - Heuristic smoke (not headline): PR-AUC **0.710**, 0 predictions at 0.83.
- **Tests:** `test_fusion.py` 1 passed (PGP vector >0.83, topic-only <0.83); `test_cases.py` 2 passed. Plus temporal 3 passed in the same pytest process (6 passed).
- **Issues / near-misses:** Feature vector is 6-D (spec §10 lists 5 plus Prompt 07 `time_missing`). Test split is denser in positives than the 2.26M candidate pool because mixed pairs drop. Do not quote 0.83-threshold recall as “the system finds 1.5% of matches in production.”
- **Judge/interview notes:** Confidence is learned, not hand-tuned. Heuristic exists and is worse. Same-handle labels are still a heuristic (Prompt 04 caveat).

### 2026-09-05 — prompts/08-graph-build.md

- **Status:** complete
- **Profile:** dev (networkx + pyvis only; Neo4j is Prompt 14)
- **What shipped:** `src/graph/build.py` (case-scoped `pair_scores` → `market:alias` graph, components → `clusters`, degree/betweenness, shared evidence with post lineage, pyvis HTML). CLI `python -m src.graph.build --case-id CASE-2026-001`. Render `docs/eval/CASE-2026-001_graph.html`.
- **Commands:** `.venv/bin/python -m pytest tests/test_graph.py -q`; `.venv/bin/python -m src.graph.build --case-id CASE-2026-001`. Did not re-run the full graph build for close-out. Lineage was queried afterward via `shared_evidence_with_lineage` (CLI JSON was truncated at 8k chars). HTML inspected as source text, not in a browser.
- **DoD:**
  - Graph @ threshold **0.83**: **n_nodes=375**, **n_edges=531**, **n_components=90** → **pass**
  - `clusters` rows **375**, matches node count → **pass**
  - 3-market component: **cluster_id 1**, **122 members**, markets **silkroad1 + silkroad2 + thehub** (not Agora/Evolution — those markets were not ingested). Date range **2011-06-18 13:10:00** … **2014-04-20 17:48:26**, **n_posts=69891**. Structural core **silkroad1:blackend646** (betweenness **0.0286**, degree centrality **0.0267**) — graph observation, not an identity claim.
  - Shared hard evidence (top hits, with lineage; `MIN()` lineage is one witnessing post per `(kind,value)`, not every post):
    - onion `dkn255hz262ypmii.onion` n_aliases=109 · `silkroad1-forums.tar.xz` / `2013-11-03` / `silkroad1-forums/2013-11-03/index.php?topic=10004.0` / sha256 `000897824ea94d40386179b94ba56629c93355438c6e20bba0aa7ccf318f41ca`
    - onion `silkroadvb5piz3r.onion` n_aliases=104 · same archive / `2013-11-03` / `…/index.php?topic=100167.0` / sha256 `001a7edb11fd5633e9946dbd554c5f77f13e905b5db3991a204059191a7de0a8`
    - clearnet `youtube.com` n_aliases=58 · `…/index.php?topic=100044.msg704491` / sha256 `0082d29c40081fb85b18b362cd41d128526b7e7e80a2d66f1a91f99ed9ac95dd`
  - HTML exists (150453 bytes). Cross-market edges `#d35400` (38 occurrences) vs same-market `#5d6d7e` (493). Physics: `toggle_physics(False)`, per-node `physics: false`, options `"enabled": false`. No live browser open in this close-out.
  - `src/graph/build.py` has no neo4j/langgraph/langchain imports. Environment: **neo4j / langgraph / langchain not installed** → **pass**
- **Tests:** `tests/test_graph.py` **2 passed in 0.12s** (known 3-alias component + loner; betweenness higher on the path bridge).
- **Issues / near-misses:** Cluster 1 is a **122-member component at 0.83**, not a tight 3-alias actor. Threshold was not lowered. Shared onions include forum-wide hosts (same class as Prompt 05 `silkroadvb5piz3r.onion` on thousands of aliases) — do not pitch those as private keys. Agora/Evolution 3-market story is not in this corpus; the real 3-span is SR1/SR2/TheHub.
- **Judge/interview notes:** `market:alias` nodes. Centrality is structural. HTML is the offline demo visual; Neo4j Browser is later.

### 2026-09-05 — prompts/09-opsec-leak-scanner.md

- **Status:** complete
- **Profile:** dev (CT live used once to seed cache; replay is cache-first. No Neo4j.)
- **What shipped:** localhost demo target (`src/opsec/demo_target/`, stdlib `http.server` not Flask), detectors in `src/opsec/scanner.py`, CT pivot `src/opsec/ct_pivot.py`, local Tor HS helper `tor_hs.py`. Findings persist to `opsec_findings` under `--case-id`.
- **Commands:** pytest `test_scanner.py` `test_ct_pivot.py` `test_cases.py`; curl of each planted path on `127.0.0.1:8080`; scanner `--target/--tls-target/--corpus`; `ct_pivot --domain erowid.org --live` then without `--live`; Tor Expert/Homebrew `tor` HS on SOCKS 19050.
- **DoD:**
  - Own HS reachable: **`rag6gxylovjpz4licuykp2pptt3rybjghniy4lmo5p4h2c3fl44xovyd.onion`** via SOCKS `127.0.0.1:19050` → HTTP 200, planted `erowid.org` img/css in body (400 bytes). Backend also verified with curl on localhost (each planted path). Tor DataDirectory in `/tmp/sutranetra-tor` because iCloud `data/tor/hs` was too permissive for Tor.
  - Scanner vs demo (actual): `clearnet_ref=erowid.org`; `server_status=demo-host.sutranetra.invalid`; `git_config=https://github.com/Venkat-Kolasani/SUTRANETRA.git`; `env_leak=/.env`; `backup_leak=/backup.zip`; `config_bak=/config.php.bak`; `dir_listing=/files/`; `server_header=Apache/2.4.41 (Ubuntu)`; `x_powered_by=PHP/7.4.3`; `default_page=/it-works` (Welcome to nginx!); `tls_san=erowid.org` (supporting detector, not headline).
  - Corpus `***clearnet***` leak (not the demo): **dangerousminds.net** on cannabisroad3 `msg_id=4111` alias `AngelEyes` · `cannabisroad3-forums.tar.xz` / `2014-11-25` / `cannabisroad3-forums/2014-11-25/index.php?topic=440.0` / sha256 `886c4ef27035ad25a1928cc1ac15ab20565b7f9771932884ae3314ef20cfb545`.
  - CT pivot `erowid.org`: live Cert Spotter **8 issuances**, sibling **`archive.erowid.org`**, 8 `pubkey_sha256` values; cache `data/cache/ct/7103f029….json`. Second run **`source=cache`** (hop `archive.erowid.org` also cache). Chain: plant clearnet img → detect `erowid.org` → pivot → `archive.erowid.org`.
  - `opsec_findings` **CASE-2026-001**: **68 rows** (11 demo kinds + 56 `corpus_clearnet` + 1 `ct_sibling=archive.erowid.org`). **CASE-2026-002: 0**.
- **Tests:** `test_scanner.py` 1, `test_ct_pivot.py` 2 (fixture, no network), `test_cases.py` 3 including case-scoped OpSec write → **6 passed in 0.75s**.
- **Issues / near-misses:** Did not add Flask (prompt allows equivalent). Tor HS keys live in `/tmp`, not git. Unauthenticated Cert Spotter used for the one `--live` seed; later demo must replay cache. TLS-SAN is implemented but must not lead the pitch. Dual `Server:` lines (Python BaseHTTP + planted Apache) — detector reports the planted Apache value.
- **Judge/interview notes:** Headline path is clearnet HTML resource → CT sibling domains. We never scanned a third-party hidden service.

### 2026-09-05 — prompts/10-explain-templates.md

- **Status:** complete
- **Profile:** dev (no Neo4j, no LLM polish; Prompt 16 not started)
- **What shipped:** `src/explain/reason.py` (structured evidence dict + `template_sentence` / `explain_pair`); `src/explain/trail.py` (`build_evidence_trail` per SPEC §15). No Ollama/LangChain.
- **Commands:** `.venv/bin/python -m pytest tests/test_reason.py tests/test_evidence_trail.py -q`; corpus DoD via `explain_pair` / `build_evidence_trail` on `data/db/attrib.sqlite` `CASE-2026-001`.
- **DoD:**
  - Preconditions: HEAD **4e74bf0** (opsec) ancestor of itself; **66f769b** (graph) is parent. `pair_scores` **2,257,292**, `clusters` **375**, `opsec_findings` **68** for CASE-2026-001.
  - 5 real pairs (mix). Two quoted sentences with backing:
    1. `` `nihilist23` (silkroad1, 2 posts) and `nxxxxxxx23` (silkroad1, 1 posts) — confidence 0.82. Shared PGP fingerprint `0551E0…D26D` in 3 posts. Stylometric similarity 0.47 (char n-gram). `` Backing: alias_ids 36079/36304; confidence **0.8194**; `s_char` **0.470**; `s_embed` **0.474**; `s_hard` **0.875**; `s_time` NULL; `n_shared_hard` **1**; PGP `0551E07ABB21CA0F02FBFBECE8ED5F45C33DD26D` in 3 posts.
    2. `` `0shit` (cannabisroad3, 1 posts) and `AlexTrusk` (cannabisroad3, 1 posts) — confidence 0.53. Stylometric similarity 0.00 (char n-gram). `` Backing: `n_shared_hard` **0**, `s_time` NULL — no PGP/BTC/temporal clauses; no `None` placeholder.
    Also generated: Platinum Standard SR2/TheHub PGP `04B63E…2C78` confidence **0.79**; QuickSilverHawk SR1/SR2 PGP `05E519…4322` confidence **0.79**; `0shit`/`Marvingaye` sparse confidence **0.51**.
  - Multi-market **cluster_id 7** (6 members, 3 markets) Evidence Trail (no fabricated CT):
    `alias` BlueSkiesRedEyes (silkroad2) → `post` #2302549 silkroad2-forums.tar.xz / 2014-01-07 / `…/topic=4619.0` sha256 `b27e2e0e…` → `evidence` PGP F30FB1D378F8978B → `alias` BlueSkiesRedEyes (thehub) → `post` #2475638 thehub-forums.tar.xz / 2014-04-21 / `…/topic=12.180` sha256 `286a2d17…` → `evidence` onion silkroad6o… → `score` fused **0.84** (S_char=0.34 / S_embed=0.66 / S_hard=0.94). Types: alias, post, evidence, alias, post, evidence, score.
  - No-OpSec/CT: pair 344/1168 (`Saul Goodman` / `pothead`, cannabisroad3) types end at `score` fused **0.84**; no `opsec`/`ct_cert`/`ct_domain`.
  - Missing `s_time`: sparse sentences omit posting-hour/UTC. Unit test covers hand-built missing-field dict.
  - Structured dict keys for Prompt 16: `case_id`, `a`, `b`, `confidence`, `s_char`, `s_embed`, `s_hard`, `s_time`, `n_shared_hard`, `shared_evidence`, `timezone`, `template_sentence`, `framing`, `system`. Full `shared_evidence` list is on the dict even when the sentence caps wallets.
  - No langchain/langgraph/langchain_ollama/ollama installed in `.venv` → **pass**
- **Tests:** `tests/test_reason.py` 1 passed; `tests/test_evidence_trail.py` 2 passed → **3 passed in 0.14s**. No skips.
- **Issues / near-misses:** Ranking `n_shared_hard DESC` hits TheHub wallet-list copypasta (118 BTC) — sentence now lists PGP + ≤2 wallets and a count of the rest; full list remains on the dict. Cluster 1 (122 members) strongest-hard path among top-centrality aliases is same-market Yoda/SelfSovereignty via shared forum clearnet, not PGP; cluster 7 is the cleaner cross-market PGP trail. Corpus `clearnet` extractor still matches filenames (`gpg.conf`); trail can surface those as evidence. `ct_sibling=archive.erowid.org` only attaches when aliases have matching clearnet evidence (demo path not glued onto every cluster).
- **Judge/interview notes:** Template prose is correlation confidence, not an identity verdict. Trail never invents OpSec/CT. LLM polish is Prompt 16.

### 2026-09-05 — prompts/11-ui-and-exports.md

- **Status:** complete (UI + exports implemented; full-case JSON/PDF on iCloud SQLite is slow — use export buttons in-session or pre-cache for demo)
- **Profile:** dev (Neo4j off, Ollama off, templates only)
- **What shipped:** `src/ui/app.py` (Streamlit investigator console — dark forensic theme, IBM Plex, gold accent, metric cards, vertical Evidence Trail timeline); `src/export/writers.py` (case-scoped `clusters.csv`, `report.json`, `report.pdf` via ReportLab); `src/opsec/scanner.py` `validate_scan_target()` (localhost-only guard shared by UI); `tests/test_export.py`.
- **Commands:** `.venv/bin/python -m pytest tests/test_export.py tests/test_evidence_trail.py -q`; `streamlit run src/ui/app.py`; corpus DoD queries on `data/db/attrib.sqlite` `CASE-2026-001`.
- **DoD (real DB, dev):**
  - Search PGP `0551E07…D26D` → **3 hits**, alias **`nihilist23`**, lineage sha256 `9440ab8f6433…` → **pass**
  - Cluster **1** trail (122 members, SR1+SR2+TheHub): types **`alias → post → evidence → alias → post → evidence → evidence`** (first 7 steps; structural clearnet path at 0.83, not PGP — same caveat as Prompt 10) → **pass**
  - Pair **`nihilist23` / `nxxxxxxx23`**: `s_char=0.470`, `s_embed=0.474`, `s_hard=0.875`, `s_time=NULL`, `confidence=0.819` — matches `pair_scores` → **pass**
  - `clusters.csv` **375 rows** for CASE-2026-001 → **pass**
  - OpSec guard rejects `https://evil.example.com` → **pass**
  - Export writers on fixture: CSV columns, JSON `evidence_trail[]` + post provenance, PDF non-empty → **pass** (`tests/test_export.py`)
  - UI loads via `streamlit run src/ui/app.py`; degraded mode shows Neo4j/Ollama off → **pass**
  - Full `report.json` (90 clusters × trail each) not re-run to completion on iCloud in this session — structure verified on fixture; expect minutes on laptop DB path
- **Tests:** `test_export.py` 1 passed; `test_evidence_trail.py` 2 passed → **3 passed in ~4s**. No skips.
- **Issues / near-misses:** Full-case JSON/PDF export over 90 clusters is IO-heavy on iCloud-hosted SQLite; PDF caps top **10** clusters with note. Large cluster (122) uses lightweight metadata in JSON (skips full post date-range scan). Ethics text is inline (Prompt 12 `docs/ethics.md` not written yet). Untracked `lib/` pyvis assets still not committed.
- **Judge/interview notes:** Evidence Trail tab calls `explain/trail.py` only — no duplicate trail logic in Streamlit. OpSec tab is localhost-constrained, not a general scanner. UI chrome reads **SUTRANETRA**, not the old working title.

### 2026-09-05 — prompts/11-ui-and-exports.md (verify + UI crash fix)

- **Status:** complete (crash fixed; views re-verified on `CASE-2026-001`, profile **dev**)
- **What changed:** Streamlit 1.63 `selectbox(range(...))` returned `None` → `TypeError: list indices must be integers or slices, not NoneType` on Clusters (whole app died because all tabs used to run). Restored missing `alias_options`. Lazy view switch (segmented control) so Search no longer loads the cluster graph. Pyvis now `cdn_resources="in_line"` (iframe no longer depends on cwd `lib/`). Dark theme via `.streamlit/config.toml`. Pair inspector defaults to `nihilist23`/`nxxxxxxx23` even though they sit at 0.819, just under the 0.83 cluster threshold.
- **DoD re-check:**
  - Search PGP `0551E07ABB21CA0F02FBFBECE8ED5F45C33DD26D` → **3 hits**, `nihilist23` / `nxxxxxxx23`, lineage `silkroad1-forums.tar.xz / 2013-11-03 / …topic=172714.0` → **pass** (browser)
  - Clusters loads without error; default cluster **#1** (122 members, 3 markets); smaller 3-market cluster **#13** (Nightcrawler, conf 0.87) also loads with members + shared evidence + pyvis → **pass** (browser)
  - Pair inspector scores **0.470 / 0.474 / 0.875 / — / 0.819** match `pair_scores` → **pass** (browser)
  - Cluster 1 trail types: `alias → post → evidence → alias → post → evidence → evidence → score → opsec×5` (OpSec steps present because findings were written under the case; not fabricated) → **pass** (Python `build_evidence_trail`)
  - OpSec scan localhost demo: **11** findings (`clearnet_ref erowid.org`, `git_config`, `env_leak`, `tls_san`, …); `https://evil.example.com` rejected → **pass**
  - Neo4j/Ollama absent; Search / Clusters / Pair / Trail still function → **pass**
- **Tests:** `tests/test_export.py` + `tests/test_evidence_trail.py` + `tests/test_graph.py` → **5 passed**. No skips.
- **Issues / near-misses:** Original UI error was the Streamlit 1.63 selectbox `None`, not a data bug. Full-case JSON/PDF still slow on iCloud SQLite. `st.components.v1.html` is deprecated in 1.63 in favor of `st.iframe(src=...)`; kept html embed because the graph is an inlined string, not a URL. Identifier-like searches skip 900k-row `posts.body LIKE` (evidence table is enough for PGP/wallets).
- **Judge/interview notes:** Confidence 0.819 on the PGP pair is honest — it is below the 0.83 cluster threshold, so those aliases are not in a cluster. Pair inspector still shows them. Green “success” badges for Neo4j-off were misleading; sidebar now states degraded mode as caption text.

### 2026-09-05 — prompts/11-ui-and-exports.md (pair default + trail expander)

- **Status:** complete (UI bugs fixed; views re-checked via Streamlit AppTest on `CASE-2026-001`, profile **dev**; live server `http://127.0.0.1:8501`)
- **What changed:** Pair inspector session keys moved to `pair_alias_a`/`pair_alias_b` (string options). Stale int indices are discarded so the default is `silkroad1:nihilist23` / `silkroad1:nxxxxxxx23`. Missing `pair_scores` rows now show a warning instead of five dashes. Evidence Trail step sequence is a caption + code block (no `st.expander`). PDF heading no longer says “Prompt 07”. Trail still calls `explain.trail.build_evidence_trail` only.
- **DoD re-check:**
  - Search PGP `0551E07ABB21CA0F02FBFBECE8ED5F45C33DD26D` → **3 hits**, `nihilist23` / `nxxxxxxx23` → **pass**
  - Clusters default **#1** (122 aliases, 3 markets, conf 0.87) + members/shared-evidence tables → **pass**
  - Pair inspector default scores **0.470 / 0.474 / 0.875 / — / 0.819** → **pass**
  - Unscored pair `silkroad1:kvalitetsbevisst` / `thehub:carlos lopez`: warning, **no** dashed metrics → **pass**
  - Cluster 1 trail types: `alias → post → evidence → alias → post → evidence → evidence → score → opsec×5`; expander count **0** → **pass**
  - OpSec tab loads findings (79 rows this DB) + CT siblings; localhost targets; no Prompt NN copy → **pass**
- **Tests:** `tests/test_export.py` + `tests/test_evidence_trail.py` → **3 passed**. No skips.
- **Issues / near-misses:** Cursor browser MCP would not keep a tab in this session (`navigate` required a tab; `tabs new` vanished). Verification used Streamlit `AppTest` against the same views. `st.components.v1.html` deprecation on Clusters is unchanged.
- **Judge/interview notes:** Dashes on S_time for the demo pair are a real NULL, not a missing row. Five dashes with a shared-onion sentence meant “never scored,” not “all zeros.”


### 2026-09-05 — prompts/12-edge-case-tests-and-ethics.md

- **Status:** complete (profile **dev**)
- **What shipped:** `src/fusion/sparse.py` (post-count gate); `pair_scores.reason` column + schema migrate; fusion score path applies gate; `patch_sparse_reasons` for already-scored cases; `src/fusion/edge_cases.py` + `docs/eval/edge_cases.json`; `docs/ethics.md`; `tests/test_edge_cases.py`. Explain templates surface `reason`.
- **Commands:** `.venv/bin/python -m src.fusion.edge_cases --case-id CASE-2026-001`; `.venv/bin/python -m pytest tests/test_edge_cases.py tests/test_fusion.py tests/test_reason.py -q`
- **DoD:**
  - **Hard-negative:** silkroad2 vendors `CaliforniaCannabis` (186) / `domesticdoode` (45) — cannabis/register overlap, `S_embed=0.824`, `S_char=0.332`, `S_hard=0`, `S_time=0.250`, **confidence=0.351 < 0.83** → **pass**
  - **Sparse:** `cannabisroad3:BHOgart` (9 posts) vs `BudsBuds` (14) — **confidence=0.35**, `reason=insufficient data` (pre-gate this class of sparse pairs reached ~0.87) → **pass**; **1,623,281** pairs patched on CASE-2026-001
  - **Paraphrase:** `Opiofile` halves — `S_char` **0.462 → 0.432** (Δ −0.030); `S_hard` **0.875** held (PGP `882B338B…4122F`); different-alias ref `Limetless` `S_char=0.476` → **pass** (honest modest degradation, not tuned)
  - `docs/ethics.md` covers all six §2 points in own words → **pass**
- **Tests:** `test_edge_cases.py` 3 passed; `test_fusion.py` 1; `test_reason.py` 1 → **5 passed**. No skips.
- **Issues / near-misses:** Sparse gate was missing before this prompt — high hard-evidence sparse pairs could score ~0.87. Char-n-gram paraphrase degradation is modest under synonym/dropout paraphrase; that is the real number, not a failure. Do not claim stylometry survives serious style change.
- **Judge/interview notes:** Correct rejection (hard-neg) is stronger than a successful match. Sparse path is enforced in code (`apply_sparse_gate`), not coincidence. Ethics: localhost-only OpSec target; CT public; identifiers ≠ verdicts.
