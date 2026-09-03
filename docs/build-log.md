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
