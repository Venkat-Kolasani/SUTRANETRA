# Prompt 00 — Project scaffold & core environment

## Objective
Stand up the repository skeleton, the SQLite schema (corpus + cases), and the core (non-agentic, non-graph-database) dependency set, so that every later prompt has a real place to put its code and a real database to write into. Nothing in this prompt scores, extracts, or attributes anything — it only builds the foundation those steps stand on.

## Spec references
`SPEC.md` §4 (repo layout), §6 / §6.1 / §6.2 (schema, source lineage columns, cases), §20 (environment).

## Preconditions
None — this is the first prompt. Confirm only that Python 3.11 (3.12 acceptable) is available.

## Detailed requirements

### 1. Repository layout
Create the full directory tree exactly as laid out in `SPEC.md` §4: `src/ingest/`, `src/evidence/`, `src/stylometry/`, `src/temporal/`, `src/fusion/`, `src/graph/`, `src/opsec/` (including an empty `demo_target/` subpackage), `src/explain/`, `src/pipeline/`, `src/agent/`, `src/export/`, `src/ui/`, `tests/`, `docs/`, `data/raw/`, `data/db/`, `data/cache/ct/`. Every `src/` subpackage gets an `__init__.py`. Do not create the individual module files listed inside each package yet (`smf_parser.py`, `pgp.py`, `trail.py`, etc.) — those belong to later prompts and creating empty stubs now just creates confusion about what's actually implemented. Exception: you may create `src/ingest/schema.py` (or equivalent) in this prompt because schema init *is* this prompt's deliverable.

### 2. `.gitignore`
`data/raw/`, `data/db/`, `data/cache/`, any `.venv`/`venv`, `__pycache__/`, `*.pyc`. The archives and the database must never be committed — they're large, regenerable, and (for the corpus) not something you want sitting in git history for a repo you might make public later.

### 3. `requirements.txt`
Only the core stack from `SPEC.md` §20 in this file: `beautifulsoup4`, `lxml`, `pandas`, `scikit-learn`, `sentence-transformers`, `faiss-cpu`, `networkx`, `pyvis`, `pgpy`, `base58`, `requests`, `streamlit`, `reportlab`, `matplotlib`, `pytest`, `scipy`, pinned to at least the minimum versions the spec gives. Do **not** add the LangGraph/LangChain/Neo4j lines yet — those are separate, later, optional installs by design (`AGENTS.md` / `CLAUDE.md` §6), and putting them in the same file now defeats the purpose of staging them.

### 4. `config.yaml`
Define the two profiles described across the spec (`dev` and `demo`, referenced explicitly in §13.1 and implied throughout). At minimum it needs: a `profile` field or CLI override, `neo4j.enabled` (false in `dev`, true in `demo`), `llm.enabled` / `llm_model` (one shared model name used by both §14 explanation polish and §16.2 the agent — this must be a single config key, not duplicated in two places), the market list to ingest, the fusion confidence threshold used for graph edges, and paths for `data/raw`, the SQLite file, and the CT cache directory. Every later module should read its configuration from this one file — nothing should hardcode a path or a threshold inline.

### 5. SQLite schema
Implement the **full** schema from `SPEC.md` §6 exactly:
- **Corpus:** `posts` (including `raw_html` and immutable lineage columns `source_archive`, `scrape_date`, `source_member_path`, `content_sha256`), `aliases`, `evidence`
- **Cases / results:** `cases`, `pair_scores` (PRIMARY KEY includes `case_id`), `clusters`, `opsec_findings`
- All indexes and UNIQUE constraints as specified (`UNIQUE(market, msg_id)`, `UNIQUE(market, alias)`, indexes on posts alias/content hash/source, evidence value, opsec case)

Write this as a schema-creation script (e.g. `src/ingest/schema.py` or a `.sql` file loaded by it) that is idempotent — running it against an already-initialized database must not error or duplicate tables.

### 6. Top-level `README.md` for the actual project (distinct from this build kit's README)
A short one: lead with **SUTRANETRA** and the tagline *"The eye that follows the hidden threads."* (one line on *sutra* / *netra*), what the system does (three layers: correlation → attribution → evidence/investigation), the legal/ethical scope statement from `SPEC.md` §2 restated in your own words, and how to run the schema init script. This is the file a judge or teammate opens first — keep it factual, not promotional.

## Explicit constraints & known gotchas
- Do not install `langgraph`, `langchain`, `langchain-core`, `langchain-ollama`, `langgraph-checkpoint-sqlite`, `neo4j`, or `langchain-neo4j` in this prompt. They come in Prompts 13 and 14, deliberately isolated so a dependency conflict in the agentic stack can never block the core pipeline from installing and running.
- The `llm_model` config key must exist even though nothing reads it yet (Prompts 10 and 15 both need it) — get the key name right now so nothing downstream has to rename it later.
- Confirm `pip install -r requirements.txt` succeeds in a clean virtual environment before declaring this step done. A requirements file that only "looks right" isn't verified.
- Do **not** implement `pipeline/case.py` business logic yet — only the empty `cases` table. Case create/open/complete lands in Prompt 07.

## Definition of Done
- [ ] `pip install -r requirements.txt` completes with no errors in a fresh virtual environment.
- [ ] Running the schema-init script against a fresh path creates `data/db/attrib.sqlite` containing exactly these tables: `posts`, `aliases`, `evidence`, `cases`, `pair_scores`, `clusters`, `opsec_findings` — verify by querying `sqlite_master` and printing the table/column list (confirm `posts` has the four lineage columns + `raw_html`, and `pair_scores` has `case_id`).
- [ ] Running the schema-init script a second time against the same database does not error and does not create duplicate tables.
- [ ] `config.yaml` parses and contains a `dev` profile with `neo4j.enabled: false` and a `demo` profile with `neo4j.enabled: true`.
- [ ] The full directory tree from `SPEC.md` §4 exists, with `__init__.py` in every `src/` subpackage.
- [ ] `git status` (or equivalent) confirms `data/`, `__pycache__/`, and virtual-env directories are ignored, not staged.

## Required tests
None yet — there is no logic to test at the scaffold stage. `tests/` should exist as an empty package (`__init__.py` only). The first real test files arrive in Prompt 01 (`test_smf_parser`, `test_dedupe`, `test_post_provenance`).

## Do not
- Do not write any parser, extractor, or scoring code in this prompt — that belongs to Prompts 01+.
- Do not pre-create placeholder/empty module files for future prompts. An empty `pgp.py` sitting in the repo before Prompt 03 makes it unclear later whether it's "not started" or "started and broken."

## Report back
State the exact `pip install` outcome, the actual table/column list printed from `sqlite_master`, and confirm both config profiles parsed correctly with their actual values. If anything in the Definition of Done required a workaround (e.g. a package version had to move off the spec's minimum), say so explicitly and why. Update `docs/build-log.md` per `AGENTS.md` §4–5.
