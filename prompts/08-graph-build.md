# Prompt 08 — Actor graph: components, centrality, and visualization

## Objective
Turn scored alias pairs into an in-process graph, cluster it into candidate actors, and produce the standalone visual render that becomes the demo's centerpiece cross-market moment. Everything in this prompt runs entirely offline, in-process, with no server dependency — that property is deliberate and must be preserved.

## Spec references
`SPEC.md` §6.2 (cases), §13 (graph build and rendering) — note that §13.1 (the Neo4j projection) is explicitly **not** part of this prompt; it's Prompt 14, and it must be built as a downstream projection of what this prompt produces, never a dependency of it.

## Preconditions
Prompt 07 complete: an active `case_id` exists and `pair_scores` is populated with calibrated confidence values for that case.

## Detailed requirements

### 1. `src/graph/build.py`
- Require `--case-id` (or equivalent). Load edges only from `pair_scores` for that case where `confidence ≥` the case's stored threshold.
- Build a `networkx` graph where each node is an alias, identified as `market:alias` (so the same username on two different markets is correctly represented as two distinct nodes until an edge links them — the graph structure itself should never conflate two aliases just because they share a display name; that conflation is exactly what the confidence-scored edge is supposed to establish, not assume).
- Add an edge between two alias-nodes wherever their pair's fused confidence meets or exceeds the case threshold, with edge weight equal to that confidence.
- Compute **connected components** — each component is a candidate actor cluster. **Persist** membership into the `clusters` table keyed by `(case_id, cluster_id, alias_id)`.
- Per cluster, compute and report: which markets it spans, its overall date range, total post count across its member aliases, all shared hard evidence items linking its members (**including post source lineage** via `evidence.post_id` → `posts`), and **degree and betweenness centrality** for each member alias — the highest-centrality alias in a cluster is the one bridging the most markets/relationships within it, which is a reasonable candidate for "primary identity" among a set of linked pseudonyms, and worth surfacing explicitly rather than leaving the cluster as an undifferentiated list.

### 2. Rendering — `pyvis`
Render the graph (or, practically, the subset of clusters worth showing — a full-corpus render may be too dense to be legible) as a standalone HTML file using `pyvis`, opening directly in a browser with no server required. Cross-market edges (an edge connecting nodes in two different markets) get a visually distinct color from same-market edges — the spec calls this out specifically as "the visual the judges remember," so it needs to actually be distinguishable at a glance, not a subtle shade difference. Disable physics simulation once the initial layout settles, or lock it off entirely — a graph that's still visibly jittering during a live demo reads as unpolished regardless of what it's showing.

## Explicit constraints & known gotchas
- This module must have zero dependency on Neo4j, LangGraph, or LangChain — none of those packages should even need to be installed for this module to run correctly. Confirm that explicitly (this is also directly checked by Prompt 12/13's `test_no_framework_leak.py`, but verify it here too rather than waiting to find out later).
- Node identity is `market:alias`, not bare `alias` — get this wrong and same-named-but-different-market aliases silently merge into one node, which defeats the entire purpose of measuring cross-market linkage.
- Centrality metrics are descriptive, not a confidence claim — "highest-betweenness alias in this cluster" is a structural observation about the graph you built, not an independently verified statement about who the real primary identity is. Word any UI/report copy accordingly.

## Definition of Done
- [ ] Report the total node count, edge count, and connected-component count for the scored graph of the active case at that case's confidence threshold.
- [ ] Confirm `clusters` rows exist for the case and match the connected components you report.
- [ ] Identify and report at least one connected component spanning 3 or more distinct markets — this is the specific demo moment the spec is building toward ("one actor across SilkRoad1, Agora and Evolution"), so confirm at least one real example exists in your data before assuming the demo script will work.
- [ ] For the multi-market cluster identified above, report its member aliases, spanned markets, date range, shared hard evidence **with at least one post's source lineage** (archive / scrape_date / member path / content_sha256), and each member's centrality score, and identify which member the centrality metrics point to as the likely core/primary alias.
- [ ] Confirm the pyvis HTML render opens correctly in a browser, cross-market edges are visually distinguishable from same-market edges by color, and the layout is stable (not actively animating) once loaded.
- [ ] Confirm this module runs with `neo4j`, `langgraph`, and `langchain` all uninstalled from the environment.

## Required tests
- A test constructing a small synthetic scored-pair set with a known expected component structure (e.g., three aliases that should merge into one cluster, one isolated alias that shouldn't) and asserting `networkx`'s connected-components output matches expectations exactly.
- A test asserting that centrality is computed and non-trivially different across members of a multi-node synthetic cluster (i.e., the computation isn't accidentally returning the same value for every node, which would indicate a bug rather than a real result).

## Do not
- Do not import `neo4j`, `langgraph`, or `langchain` anywhere in this module.
- Do not conflate `market:alias` identity — always key nodes by the full pair.

## Report back
Report the graph-level counts, the identified multi-market cluster with full detail, the render verification, the framework-independence confirmation, and both test results.
