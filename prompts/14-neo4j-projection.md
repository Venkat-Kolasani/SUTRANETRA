# Prompt 14 — Neo4j projection of the finished graph

## Objective
Project the already-computed, already-correct graph from Prompt 08 into Neo4j, purely to enable ad-hoc Cypher querying, an interactive Neo4j Browser visualization, and a genuine multi-user query story. `networkx` remains the compute engine for everything that determines correctness (components, centrality, thresholding) — Neo4j receives a finished result and must never become something the attribution logic depends on to run.

## Spec references
`SPEC.md` §13.1 in full, including the RBAC caveat about Community Edition's limited read-only role support.

## Preconditions
Prompt 08 (graph build) complete and verified. Neo4j Community Edition installed locally (zip or Desktop distribution — no Docker required, no license, JVM bundled).

## Detailed requirements

### 1. `src/graph/neo4j_sink.py`
Implement the node/relationship model exactly as specified: `Alias` nodes (name, market, post count, first/last seen, vendor flag, centrality), `Actor` nodes (cluster id, alias count, markets spanned, max confidence), `Evidence` nodes (kind, value), `Domain` nodes (name, source), with `MEMBER_OF` (alias → actor), `LINKED_TO` (alias → alias, carrying confidence and the individual feature scores plus a cross-market flag), `USED` (alias → evidence), and `PIVOTS_TO` (evidence → domain, from Prompt 09's CT-pivot results).

### 2. Load discipline
Create uniqueness constraints on `Alias(market, name)` and `Evidence(kind, value)` **before** loading any data — without them, `MERGE` degrades to a full scan per row and a full-corpus load takes minutes instead of seconds. Batch the load using `UNWIND` + `MERGE` in transactions of a few thousand rows at a time, not row-by-row. The load must be idempotent — running it twice against the same graph must not create duplicate nodes/relationships or error, since a failed mid-demo load needs to be simply re-runnable.

### 3. Two config profiles, and getting the default direction right
The sink runs strictly **after** `graph/build.py` and is skippable entirely via a `--no-neo4j` flag. `config.yaml`'s `dev` profile has the sink **off** by default (no server needed while iterating on everything upstream of it); the `demo` profile has it **on**. Get this the right way around — `--no-neo4j` is meant to be the panic switch used if the server won't start on the day, not the default state you forgot to flip before the actual demo. Confirm which profile is active is always visible/logged, so it's never ambiguous which mode a given run used.

### 4. Read-only access — verify the actual enforcement, don't assume it
Set up a Neo4j user intended for read-only query access, used both by the query console in the UI and by Prompt 15's agent tool. **Explicitly verify** whether Community Edition's role/permission system actually supports granting a genuinely enforced read-only role in your installed version — the spec flags this as a real, version-dependent limitation, not a guaranteed feature. If a true read-only role isn't available in your installed Community Edition version, fall back to a separate database instance with no write path wired into anything that reads from it, and **state this limitation explicitly** in the project's documentation rather than claiming an enforcement guarantee the deployment doesn't actually have. This verification needs to happen now, at this step — not discovered later when Prompt 15's agent-safety claims turn out to rest on an assumption that was never actually checked.

### 5. Rehearsed Cypher queries
Implement and rehearse (i.e., actually run against your real loaded data, not just write and assume they're correct) the four queries the spec calls out as the demo path: actors spanning three or more markets ranked by confidence; the shortest evidence path between two named aliases; wallets/evidence items shared by more than one alias, ranked by how many; and the onion-leak → clearnet-domain → sibling-infrastructure walk that renders capability #1 as a single graph query. That last one is worth extra rehearsal — it's the query that visually tells the whole de-anonymization story in one picture.

### 6. Guardrail: Neo4j down must never break anything upstream
Confirm explicitly that with Neo4j stopped or `--no-neo4j` set, the `pyvis` render from Prompt 08 and every export from Prompt 11 still work correctly and completely. This is the direct test of the "optional at runtime" invariant from `CLAUDE.md` §2.

## Explicit constraints & known gotchas
- Do not skip the uniqueness constraints before loading — the performance difference at real corpus scale (tens of thousands of nodes) is the difference between a load that fits inside a demo rehearsal and one that doesn't.
- Do not assume Community Edition's RBAC grants a real read-only role without checking your actual installed version — this is explicitly called out as untested-by-default in the spec, and `test_cypher_readonly.py` (Prompt 15) tests the query-rejection *regex*, which will pass regardless of whether the underlying database connection is actually read-only. The regex and the connection-level enforcement are two separate controls; verify both, and don't let a passing regex test stand in for a verified read-only connection.
- `langchain-neo4j`'s prebuilt Cypher-generation chain is worth trying but is explicitly a bonus, shown only after the four hand-written, rehearsed queries have already landed — a chain that generates incorrect Cypher live is a worse outcome than showing fewer, reliable queries.

## Definition of Done
- [ ] Uniqueness constraints exist on `Alias(market, name)` and `Evidence(kind, value)`, confirmed by querying the database's own constraint listing.
- [ ] Load the full corpus's graph into Neo4j and report the actual load time — confirm it's fast (seconds, not minutes) as a direct check that the constraints are actually in effect.
- [ ] Run the load a second time against the same database and confirm no duplicate nodes/relationships resulted.
- [ ] Run all four rehearsed Cypher queries against the real loaded data and report their actual output — in particular, run the onion-leak → domain → siblings query against the real leak/pivot data from Prompt 09 and confirm it renders the full chain correctly.
- [ ] Explicitly report the outcome of the read-only-role verification from step 4: does your installed Community Edition version actually support an enforced read-only role, yes or no, and which approach (real role, or separate no-write-path database) you ended up using as a result.
- [ ] Stop the Neo4j server (or set `--no-neo4j`) and re-verify that Prompt 08's pyvis render and Prompt 11's three export formats all still work correctly.

## Required tests
None new beyond what Prompt 15 adds (`test_cypher_readonly.py`) — this prompt's correctness is verified primarily through the manual load/query/degraded-mode checks above, since they depend on a running Neo4j instance that automated CI-style tests in this project aren't expected to spin up.

## Do not
- Do not load without the uniqueness constraints in place first.
- Do not claim a read-only enforcement guarantee without having actually verified it against your installed Community Edition version.
- Do not let anything upstream of this prompt come to depend on Neo4j being available.

## Report back
Report the constraint verification, the load time and idempotency check, the four rehearsed queries' actual output, the explicit read-only-role verification outcome (and which fallback, if any, you used), and the Neo4j-down degraded-mode re-verification.
