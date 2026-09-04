# Prompt 15 — Investigator agent, guardrails, and the Cypher query tool

## Objective
Build the natural-language query layer over the already-complete, already-correct pipeline. This is explicitly the part of the demo judges remember — and it is also the part most likely to be misunderstood as "the AI is deciding who's guilty" if the guardrails aren't both real and clearly communicated. This prompt builds both the capability and the enforcement, and treats them as equally important.

## Spec references
`SPEC.md` §16.2, §16.3, §16.4, and the agent-tool callout at the end of §13.1 (`cypher_query`).

## Preconditions
Prompt 13 (LangGraph wrapper, and the agentic dependency install) and Prompt 14 (Neo4j projection, including its read-only-role verification result) complete. Build this only after the pipeline produces real clusters to query — there is nothing meaningful to build a query layer over until then.

## Detailed requirements

### 1. Tools — `src/agent/tools.py`
Implement each of the following as a distinct, narrowly-scoped, **read-only** tool, each a thin call onto a function that already exists from earlier prompts (do not write new business logic here):
- `search_evidence`: find every alias linked to a given wallet, PGP fingerprint, onion address, or clearnet domain (include post lineage in returned rows).
- `get_cluster`: return a cluster's members, spanned markets, confidence, and shared evidence, given one alias in it (case-scoped).
- `score_pair`: return the stored per-feature scores and fused confidence for a specific alias pair (case-scoped).
- `evidence_trail`: return the ordered Evidence Trail for a cluster or pair under a `case_id` — thin wrapper over `explain.trail.build_evidence_trail`.
- `get_case`: return case metadata (corpus snapshot, config hash, model version, threshold, status).
- `alias_timeline`: return an alias's posting activity over time, its hour-of-day histogram, and its estimated UTC offset.
- `ct_pivot`: run the cache-first Certificate Transparency pivot from Prompt 09 for a given domain.
- `opsec_scan`: run the misconfiguration scanner from Prompt 09 — this is the **only** tool with any side effect (it makes outbound requests), and it must be constrained to localhost/explicitly-configured demo targets only, exactly as the scanner module itself was already constrained in Prompt 09/11.
- `cypher_query`: run a read-only Cypher query against the Neo4j projection from Prompt 14, rejecting any query containing `CREATE`, `MERGE`, `DELETE`, `SET`, or `DROP` (case-insensitively, including when the query starts with leading whitespace before the keyword).

Every tool's docstring should be written as a clear instruction to the model about exactly when to use it and what it returns — this is what a tool-calling model actually reads to decide which tool fits a given question, so vague or generic docstrings directly hurt tool-selection accuracy.

### 2. Model
Use `ChatOllama` with `temperature=0` and the same `llm_model` config key Prompt 10 already established — this must remain one shared value, not a second model config, for the RAM-budget reason already stated in Prompt 10. If tool-selection reliability is weak on a smaller model, the spec notes a mid-size model tends to be meaningfully stronger at tool selection than a small one, within whatever memory budget your development machine has.

### 3. Guardrails — enforced, not just documented
- **The agent never computes a verdict.** Every tool (other than `opsec_scan`) is read-only over already-computed data (`pair_scores`, `evidence`, the graph). The agent retrieves and phrases results; the deterministic pipeline built in Prompts 01–10 is what decided them.
- **No tool writes to the database.** Enforce this with an actual read-only SQLite connection mode (`file:...?mode=ro`) used by the entire agent process, and the read-only Neo4j access path verified/established in Prompt 14 — this is a connection-level control, not a convention or a comment saying "please don't write here."
- **Every answer carries provenance.** Tool outputs include the underlying row identifiers, and the UI (extending Prompt 11's Streamlit app) renders the actual evidence rows beneath whatever text the agent generates, so a judge can always see the source data behind a claim rather than trusting the agent's prose on its own.
- **Graceful offline degradation.** If Ollama is unreachable, the investigator console must degrade to the structured search/filter UI from Prompt 11 rather than presenting a broken or hung chat interface — verify this explicitly, the same way Prompt 10 required for the explanation-polish path.

### 4. Rehearsed queries
Get at least three natural-language queries working reliably end-to-end, using real data from your corpus — for example, a query that surfaces which aliases shared a specific PGP key with a named alias, a query that asks for the **Evidence Trail** for a named cluster/case, and — the one worth rehearsing hardest — a query that requires the agent to chain two tools in one turn (`search_evidence` then `ct_pivot`, following a clearnet-domain leak through to the operator's other infrastructure). Cache or pin the Ollama model locally ahead of time; never plan to download a model on the day of the demo.

## Explicit constraints & known gotchas
- Before writing any of this, inspect the actually-installed LangChain package's tool-calling API directly rather than trusting a remembered shape from training or an online tutorial — this is the same warning as Prompt 13 step 2, and it applies with equal force here.
- The `cypher_query` regex rejection is a courtesy layer, not the actual control — the actual control is the read-only database connection/role established (or, if unavailable, honestly substituted for) in Prompt 14. Do not let a passing regex test create false confidence about database-level write protection.
- Keep the tool count focused (spec now includes `evidence_trail` and `get_case` in addition to the earlier set) and cap agent iterations — an agent that loops or picks the wrong tool repeatedly is a worse demo failure mode than a slightly less capable one that answers reliably.
- Rehearsed queries are the demo path; free-form natural-language querying is the bonus shown only if time and confidence allow — do not build the demo script around the assumption that arbitrary free-form questions will always route correctly.

## Definition of Done
- [ ] Every tool in `src/agent/tools.py` is confirmed to hold a read-only connection (SQLite `mode=ro`, or the equivalent read-only Neo4j access path) — verify this by attempting a write through the agent's connection object directly and confirming it's rejected at the connection/permission level, not just skipped by convention.
- [ ] `search_evidence`, `get_cluster`, `score_pair`, `evidence_trail`, `get_case`, `alias_timeline`, `ct_pivot`, and `cypher_query` each independently return correct results against real data you can verify by hand (spot-check at least one call per tool against the underlying database directly).
- [ ] `opsec_scan` is confirmed to reject or refuse a non-localhost/non-demo-target input.
- [ ] The three rehearsed natural-language queries (including the Evidence Trail query and the two-tool chained one) each produce a correct answer with visible provenance (the underlying evidence rows / trail steps shown alongside the agent's text) — report the actual question asked and the actual answer produced for all three.
- [ ] Stop Ollama and confirm the investigator console degrades to the structured search UI rather than hanging or erroring.

## Required tests
- `tests/test_cypher_readonly.py` — `cypher_query` rejects queries containing `CREATE`, `MERGE`, `DELETE`, `SET`, or `DROP`, including mixed-case keywords and queries with leading whitespace before the keyword.
- `tests/test_agent_readonly.py` — every tool in `src/agent/tools.py` is confirmed, programmatically, to hold a connection opened in read-only mode; attempting a write operation through that connection raises rather than silently succeeding.
- Extend `tests/test_no_framework_leak.py` (from Prompt 13) to also assert that nothing outside `src/graph/neo4j_sink.py` and `src/agent/` imports `neo4j` — this completes the "wrapper, not owner" check for the graph-database boundary the same way it already covers the LangChain/LangGraph boundary.

## Do not
- Do not let any agent tool other than `opsec_scan` have a side effect.
- Do not treat the `cypher_query` regex test as proof that write access is blocked — verify the connection-level control separately, and be honest in your reporting if Prompt 14's read-only-role verification came back negative for your Neo4j version.
- Do not build the demo around free-form querying working reliably — the three rehearsed queries are the actual deliverable.

## Report back
Report the read-only-connection verification for every tool, the per-tool spot-check results, the `opsec_scan` scope-rejection confirmation, the three full rehearsed query transcripts with their provenance, the Ollama-down degradation confirmation, and all three test results (including the extended framework-leak test).
