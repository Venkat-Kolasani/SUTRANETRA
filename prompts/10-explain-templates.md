# Prompt 10 — Explanation templates + Evidence Trail builder

## Objective
Turn a scored, evidenced alias pair or cluster into (1) a readable, factually-grounded sentence a human investigator can act on, and (2) an **ordered Evidence Trail** — the vertical forensic chain that answers *"How did your system reach this conclusion?"* Both are deterministic, offline, and have zero dependency on any external model. The trail is the single best UI primitive for this project; Prompt 11 only renders what this prompt builds.

## Spec references
`SPEC.md` §14 (template prose + trail), §15 (Evidence Trail shape), §6.1 (post lineage on every post step). The optional LLM-polish portion of §14 is deliberately **not** part of this prompt; it's Prompt 16.

## Preconditions
Prompt 07 (fusion scores + cases), Prompt 03 (evidence), and Prompt 08 (clusters persisted for a case) complete. Prompt 09 (opsec findings) should be complete if you want CT steps in the trail; if not, trails omit OpSec/CT nodes rather than fabricating them.

## Detailed requirements

### 1. `src/explain/reason.py`
Given a scored pair's stored features (fused confidence, `S_char`, shared evidence rows, temporal overlap/timezone estimate, post counts, markets), generate a factual, structured sentence in the style of the spec's own worked example: name both aliases with their market and post count, state the confidence, and enumerate the specific shared evidence (fingerprint, wallet, stylometric score, temporal signal) that produced it. Every claim in the generated sentence must trace back to an actual stored value for that pair — no generic filler phrases, and nothing stated that isn't backed by a specific field in `pair_scores`/`evidence`.

### 2. Structure the output as data, not just a string
Have the generator produce (or be trivially derivable into) the same structured evidence dictionary shape that Prompt 16's LLM-polish step will later consume as its only input. Design this shape now, even though nothing reads it as structured data yet, so Prompt 16 doesn't need to retrofit a parallel data path — one structured representation, rendered as a template sentence here and optionally rewritten by a model later.

### 3. `src/explain/trail.py` — Evidence Trail
Implement `build_evidence_trail(db, case_id, *, cluster_id=None, a_alias_id=None, b_alias_id=None) -> list[dict]` per `SPEC.md` §15:
- Return an **ordered** list of typed steps: `alias` | `post` | `evidence` | `score` | `opsec` | `ct_cert` | `ct_domain`.
- Prefer the strongest hard-evidence path between the two highest-centrality (or selected) aliases in a cluster, then append fused confidence, then any case-scoped OpSec/CT steps linked to those aliases' clearnet evidence.
- Every `post` step **must** include `source_archive`, `scrape_date`, `source_member_path`, `content_sha256`.
- Include underlying row ids on every step so UI/export/agent can deep-link.
- **Never invent steps.** If the case has no OpSec/CT findings for this cluster, omit those nodes.
- Fully deterministic; no LLM; no LangChain.

### 4. Determinism and independence
Both modules must be fully deterministic, fast, and have zero dependency on Ollama, LangChain, or any other model/framework package — confirm they run correctly in an environment where none of those are installed at all.

## Explicit constraints & known gotchas
- Do not build any Ollama/LLM integration in this prompt — that is explicitly Prompt 16's job.
- Do not let template generation silently produce a sentence with a missing/null field rendered as blank or as a placeholder like "None" — if a piece of expected evidence is absent for a given pair, the sentence should simply not mention that category, not mention it with a broken value.
- Do not fabricate CT/OpSec trail steps to make the demo look longer.

## Definition of Done
- [ ] Generate template explanations for at least 5 real scored pairs from your corpus (a mix of high-confidence, evidence-rich pairs and lower-confidence, evidence-sparse ones) and confirm every factual claim in each generated sentence traces back to an actual stored value — quote at least 2 full generated sentences alongside the underlying data that produced them.
- [ ] For at least one multi-market cluster, print the full Evidence Trail (step types + labels) and confirm it matches the underlying rows, including post lineage on every post step.
- [ ] Confirm a cluster/pair with no OpSec findings produces a trail that ends at confidence (or corpus clearnet evidence only) without fabricated CT nodes.
- [ ] Confirm both modules run correctly in an environment with no `langchain`/`langgraph`/Ollama-related packages installed at all.
- [ ] Confirm a pair with a missing/null feature (e.g., no temporal signal) produces a sentence that omits that category cleanly rather than rendering a broken or null-looking value.
- [ ] Confirm the structured evidence dictionary this module produces contains everything Prompt 16 will need as its LLM-polish input.

## Required tests
- A test asserting the template generator produces the expected sentence structure and includes every piece of evidence present in a hand-constructed input evidence dict, and excludes anything not present in it (including the missing-field case above).
- `tests/test_evidence_trail.py` — synthetic case with two aliases, shared PGP on known posts (with lineage), fused score, and a clearnet→CT stub: `build_evidence_trail` returns ordered steps of the expected types; every `post` step includes source lineage; no fabricated OpSec steps when none exist; when CT stub is present, `ct_domain` appears after clearnet.

## Do not
- Do not build any LLM/Ollama integration in this prompt.
- Do not render a missing feature as a null-looking placeholder in the output sentence.
- Do not invent trail steps.

## Report back
Quote two template explanations with their backing data, print one full Evidence Trail for a real cluster, report both test outcomes, and update `docs/build-log.md`.
