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
