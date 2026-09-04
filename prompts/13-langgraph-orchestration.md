# Prompt 13 — LangGraph pipeline orchestration (thin wrapper, not owner)

## Objective
Wrap the seven already-working pipeline stages (ingest, evidence, stylometry, fusion, graph, opsec, explain) as nodes in a `LangGraph` `StateGraph`, purely for checkpoint/resume, a genuine parallel branch, and an auto-generated architecture diagram. Nothing about *what* the pipeline computes changes in this prompt — only *how it's driven*.

## Spec references
`SPEC.md` §16.1 in full, including the explicit warning about `SqliteSaver`'s construction contract having changed across LangGraph versions.

## Preconditions
Prompts 01–10 complete and individually verified — every stage this prompt wraps must already work correctly as a standalone, callable function/CLI before it's wrapped. This prompt adds orchestration around working logic; it does not fix or complete any stage's own correctness.

## Detailed requirements

### 1. Install order
This is the first prompt where the agentic dependency group gets installed — do it as a separate, explicit step, confirmed not to disturb the already-working core pipeline. Pin the package versions your environment actually resolves to for `langgraph`, `langchain`, `langchain-core`, `langchain-ollama`, and `langgraph-checkpoint-sqlite` (re-verify current version numbers rather than trusting any older reference, per `CLAUDE.md` §6 and `docs/VALIDATION-AND-NOVELTY.md` §3 — both frameworks release frequently enough that any previously-written pin should be treated as a starting point to confirm, not a fact to assume).

### 2. Before writing any agent/graph code
Inspect the actually-installed package's public API directly (e.g., list what's exposed by the relevant module) rather than working from a remembered API shape or an online tutorial — this section of LangChain/LangGraph has been renamed and restructured across major versions, and the spec calls this out as the single biggest time sink in this part of the build if skipped. In particular, confirm the exact construction contract for the checkpointer (`SqliteSaver` or its current equivalent) before writing the line that instantiates it — the spec notes it may currently be a context manager rather than a plain constructor, which is exactly the kind of detail that differs between versions and silently produces the wrong object type if assumed.

### 3. `CaseState` and the graph shape
Define a typed state object carrying: case id (**must equal `cases.case_id`**), the market list being processed, and running counts/results from each stage (posts, aliases, evidence, candidate pairs, scored pairs, clusters, opsec findings, and an errors list). On START, ensure the case row exists via `pipeline/case.py` and set `status='running'`; on END, set `complete` or `failed`. Wire seven nodes — `ingest`, `evidence`, `stylometry`, `fusion`, `graph`, `opsec`, `explain` — with this dependency structure: ingest feeds evidence; evidence fans out to both `stylometry` and `opsec` as two genuinely independent branches (opsec does not need fusion's output, so there's no reason to force it to wait); `stylometry` feeds `fusion`; `fusion` feeds `graph`; both `graph` and `opsec` join at `explain`, which is the point that needs both branches' output before it can produce a full explanation **and Evidence Trail** for a cluster (correlation results plus any opsec findings relevant to it). Scoring/graph/opsec nodes write only under `state["case_id"]`.

### 4. The hard rule: every node is a thin wrapper
Each node function does exactly one thing: call the already-existing, already-tested module function for that stage (e.g., `evidence.extract.run(db)`), and return whatever summary values belong in `CaseState`. **Zero business logic lives inside a node.** Every stage must remain independently runnable from its own CLI entry point exactly as it was before this prompt — verify this explicitly, don't just assume wrapping didn't change anything.

### 5. What this buys, concretely — and how to prove it
- **Checkpoint/resume**: persist state per node via the checkpointer. Actually kill a run partway through (mid-ingest or mid-fusion) and confirm resuming from the checkpoint continues from where it stopped rather than restarting from scratch. This needs to be demonstrated, not assumed to work because the checkpointer is configured.
- **Genuine parallel branch**: confirm `opsec` and `stylometry`/`fusion` actually execute concurrently rather than sequentially — time a run and confirm the wall-clock behavior is consistent with parallel execution, not just trust the graph edges you wrote.
- **Generated architecture diagram**: use the graph's own diagram-export capability (e.g., a Mermaid PNG export) to produce `docs/architecture.png` from the actual compiled graph — this replaces any hand-drawn box diagram with one generated directly from the code that runs, which is a stronger claim in a pitch deck than a diagram someone drew by hand and which could drift from reality.

## Explicit constraints & known gotchas
- Do not put any extraction, scoring, or decision logic inside a node function. If a node function is longer than a few lines beyond "call the existing function, shape the return value," that's a sign business logic leaked into the wrapper.
- Do not assume the checkpointer's constructor signature from memory — confirm it against the installed package first, per step 2.
- Confirm the core pipeline (Prompts 01–10) still works correctly with `langgraph`/`langchain` fully uninstalled — if it doesn't, something got coupled to the framework that shouldn't have been.

## Definition of Done
- [ ] `pip install` of the agentic dependency group succeeds without breaking the already-installed core stack — confirm by re-running one of the earlier prompts' Definition-of-Done checks (e.g., re-run the fusion evaluation) after this install and confirm it still works identically.
- [ ] Run the full pipeline end-to-end through the compiled `StateGraph` and confirm it produces output consistent with running the stages individually via their own CLIs.
- [ ] Kill a run mid-execution and demonstrate a resume from checkpoint that does not re-do already-completed work.
- [ ] Demonstrate (with timing evidence) that `opsec` and the `stylometry`→`fusion` chain execute in parallel rather than sequentially.
- [ ] `docs/architecture.png` exists, was generated from the compiled graph object (not hand-drawn), and accurately reflects the node/edge structure described in step 3.
- [ ] Delete or bypass `src/pipeline/graph.py` and confirm every individual stage still runs correctly from its own CLI entry point — this is the direct, concrete proof of the "wrapper, not owner" invariant from `CLAUDE.md` §2.

## Required tests
- `tests/test_no_framework_leak.py` — walk every `.py` file under `src/` using Python's `ast` module, parse its imports, and assert that nothing outside `src/pipeline/` and `src/agent/` imports `langchain`/`langgraph` (Prompt 15 will extend this same test to also check the `neo4j` import boundary — write it now scoped to the langchain/langgraph boundary, and leave it structured so Prompt 14/15 can add to it rather than replacing it). This test is what makes the wrapper-not-owner claim checkable rather than aspirational — write it as soon as this section exists, not as a final cleanup step.

## Do not
- Do not put business logic inside a node.
- Do not skip confirming the checkpointer's actual construction contract against the installed version.
- Do not treat "the graph compiled without error" as equivalent to "checkpoint/resume actually works" — demonstrate the resume.

## Report back
Report the install verification, the end-to-end run result compared against standalone CLI runs, the demonstrated checkpoint/resume, the parallel-execution timing evidence, confirmation `docs/architecture.png` was generated (not drawn), the delete-and-still-works verification, and the `test_no_framework_leak.py` result.
