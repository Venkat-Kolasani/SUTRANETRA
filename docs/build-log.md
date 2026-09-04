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

- **Status:** partial (code + unit tests; full-corpus extract blocked on Prompt 02 ingest)
- **Profile:** dev
- **What shipped:** `src/evidence/{pgp,crypto_addr,onion,extract,score,htmltext}.py`; fixture `tests/fixtures/pgp_trappy_msg1596.asc` (cannabisroad3 msg 1596 / Trappy).
- **DoD:**
  - evidence populated across full corpus → **not run** (Silk Road 1 ingest still in progress; did not write `evidence` on the live DB)
  - per-kind counts / 10-row spot-check / multi-alias shared PGP or wallet → **pending** full extract
  - shared-evidence score: one PGP → **0.875** (`1 - 0.5^3`, spec ~0.88); empty pair → **0** → **pass** (unit)
- **Tests:** `test_crypto_addr.py` 3 passed (4 real CR3 addresses valid; MD5 `16936e5adb8a36cbb21d38beeb6f8e11` and short `3y4kBQhzP5dPh1AiMhNWU7HKLB3` rejected); `test_pgp.py` 5 passed (fingerprint `74D0519647C44BCBC03A182421819BFFDB3D03BC`); `test_evidence_extract.py` 2 passed (`dangerousminds.net` from topic 440). **10 passed in 0.11s**
- **Issues / near-misses:** `pgpy` imports removed-stdlib `imghdr` on Python 3.13 — stubbed in `pgp.py`. ~6 CR3 pubkey blocks fail `PGPKey.from_blob` (scrape-mangled armor); fallback keeps Key ID rather than dropping. Keccak-256 for Monero is local (hashlib SHA3 is the wrong padding).
- **Judge/interview notes:** Regex-only BTC is the credibility trap; the unit test is the proof, not the extractor existing.

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
