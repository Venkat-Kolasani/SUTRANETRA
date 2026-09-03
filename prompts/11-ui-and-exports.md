# Prompt 11 — Streamlit UI, Evidence Trail tab, and CSV/JSON/PDF exports

## Objective
Build the surfaces a human investigator (or a judge) actually interacts with, and the three output formats the problem statement names explicitly. This includes the **Evidence Trail** tab — the vertical forensic chain that visually answers *"How did your system reach this conclusion?"* — which the spec calls out as the single best UI element for the project. Exports and query UI are "free marks left on the table" if skipped; the trail is not optional polish.

## Spec references
`SPEC.md` §15 (full), §6.1 (lineage), §6.2 (cases), §14 (`explain/trail.py` from Prompt 10).

## Preconditions
Prompts 07 (fusion + cases), 08 (graph + clusters), 09 (opsec findings), and 10 (reason + trail) complete — this prompt is a consumer of all of them, not a producer of new signal.

## Detailed requirements

### 1. `src/ui/app.py` — single-file Streamlit app
- **Case selector**: pick an active `case_id`; show corpus snapshot, model version, threshold, config hash, status. All other views are scoped to that case. App chrome / page title must read **SUTRANETRA** (and optionally the tagline in small text) — not the old working title.
- **Search**: full-text search across `evidence` and `posts` by alias, wallet address, PGP fingerprint, onion address, or clearnet domain, returning matching rows with enough context to be useful (which post, which alias, which market) **and post source lineage**.
- **Actor cluster view**: a list of clusters for the active case sorted by confidence, where selecting one shows its member aliases, the evidence table backing the linkage (with provenance), and the embedded `pyvis` graph for that cluster specifically (not the whole corpus graph, which would be too dense to be readable inline).
- **Pair inspector**: pick two aliases, show the full per-feature score breakdown (`S_char`, `S_embed`, `S_hard`, `S_time`, fused confidence) side by side, the specific shared-evidence rows with their surrounding context text **and source lineage**, and the generated explanation from Prompt 10.
- **Evidence Trail tab** (headline view): given a selected cluster or pair under the active case, call `explain.trail.build_evidence_trail` and render a **vertical ordered chain** (alias → post → evidence → … → confidence → clearnet → CT → sibling domain). Each step shows its type/label and, for posts, archive / scrape_date / member path / content_sha256. This must be readable in a screenshot — it is the demo's "how did you get here?" answer. Missing OpSec/CT branches are omitted, never faked.
- **OpSec scan tab**: a form to run the scanner (from Prompt 09) against a target — default it to the demo target, and constrain it so it cannot be pointed at an arbitrary live third-party host from the UI — showing the findings and the resulting CT-pivot sibling domains as a small graph or list; writes under the active case.
- **Export buttons** on every view above, wired to the export writers in step 2.

### 2. `src/export/writers.py` (keyed by `case_id`)
- `clusters.csv`: one row per (cluster, member alias), including `case_id`, `cluster_id`, `alias`, `market`, `n_posts`, `confidence`, and a short evidence summary string.
- `report.json`: the full nested structure — case metadata, clusters, member aliases, each alias's evidence, **post provenance**, per-feature pairwise scores, **`evidence_trail[]`**, generated explanation, opsec findings — structured so that a downstream tool (or a human reading raw JSON) can reconstruct the full forensic chain without needing the database.
- `report.pdf` (via ReportLab): a cover page **branded SUTRANETRA** with the case card and tagline, a methodology section (in plain language — what signals were combined and how), one page per cluster (graph image, evidence table, **Evidence Trail**, generated explanation), the ethics statement (from Prompt 12), and an evaluation-metrics appendix (the numbers produced in Prompt 07/12). Set `cases.report_path` when written.

## Explicit constraints & known gotchas
- The OpSec scan tab must not become a general-purpose scanner-as-a-service against arbitrary URLs — constrain it to localhost/demo-target-style inputs, consistent with the scope constraint already established in Prompt 09.
- Every view must degrade gracefully if optional dependencies (Neo4j, Ollama) aren't available — Search, Cluster, Pair Inspector, and Evidence Trail have no reason to depend on either.
- `report.pdf` generation over a large corpus (many clusters) could get slow or produce an unreasonably long document — cap or paginate sensibly (e.g., top-N clusters by confidence, with a note that the full JSON export has everything).
- If time forces a cut inside this prompt, cut PDF polish before cutting the Evidence Trail tab (`SPEC.md` §15).

## Definition of Done
- [ ] Launch the Streamlit app (`streamlit run`) and confirm case selector + all views load without error against the real populated database.
- [ ] Search for a known wallet address or PGP fingerprint (one you verified manually in Prompt 03) and confirm it returns the correct matching aliases/posts **with lineage**.
- [ ] Open the multi-market cluster identified in Prompt 08 through the Actor cluster view and confirm the embedded graph, evidence table, and member list match what you already verified there.
- [ ] Open the **Evidence Trail** tab for that cluster and confirm the vertical chain matches Prompt 10's trail output (quote the step sequence in your report).
- [ ] Run the Pair Inspector on a known high-confidence pair and confirm the per-feature score breakdown matches the values stored in `pair_scores` for the active case.
- [ ] Run the OpSec tab against the demo target from Prompt 09 and confirm it reports the same findings as the standalone scanner did and writes under the active case.
- [ ] Generate `clusters.csv`, `report.json`, and `report.pdf` from the UI's export buttons; confirm `report.json` contains `evidence_trail` and post provenance; spot-check at least one cluster across all three formats.
- [ ] Confirm the UI's core views (Search, Cluster, Pair Inspector, Evidence Trail) function correctly with Neo4j and Ollama both absent/unreachable.

## Required tests
- A test that calls each export writer against a small, known fixture dataset (including a prebuilt trail) and asserts the output file's structure/content matches expectations (correct columns in the CSV, correct nested keys including `evidence_trail` and provenance in the JSON, and — at minimum — that the PDF generation call completes without raising and produces a non-empty file).
- Re-run `tests/test_evidence_trail.py` to confirm the UI still consumes the same trail builder (no duplicate trail logic inside Streamlit).

## Do not
- Do not allow the OpSec scan tab to accept an arbitrary external URL without the same scope constraints enforced in the scanner module itself.
- Do not let any of the core views hard-fail if Neo4j or Ollama is unavailable.
- Do not reimplement trail construction inside the UI — call `explain.trail`.
- Do not ship without the Evidence Trail tab.

## Report back
Report the view smoke-test results (including the Evidence Trail step sequence for the demo cluster), export verification, degraded-mode confirmation, test results, and update `docs/build-log.md`.
