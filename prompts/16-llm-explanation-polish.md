# Prompt 16 — Ollama explanation polish (optional, final step)

## Objective
Add a local-LLM rewrite on top of the already-complete, already-correct template explanations from Prompt 10 — pure prose polish, never a new source of facts and never a decision-maker. This is the last item in the build order deliberately: it reuses the exact `ChatOllama` setup Prompt 15 already stood up for the investigator agent, rather than configuring a second, separate model.

## Spec references
`SPEC.md` §14 (LLM-polish portion).

## Preconditions
Prompt 10 (template explanations, including the structured evidence dictionary shape) and Prompt 15 (investigator agent, `ChatOllama` configuration, and the shared `llm_model` config key) both complete.

## Detailed requirements

### 1. The rewrite function
Take the structured evidence dictionary Prompt 10 already produces for a scored pair and pass it — and **only it** — to `ChatOllama`, configured with the same `llm_model` key from `config.yaml` that Prompt 15's investigator agent already uses. This must be the same configured model, not a second one: running two different local models resident in memory at once is a realistic way to exhaust RAM on an 8 GB demo machine, and the spec is explicit that this is a one-key, shared setting, not two.

### 2. What the model may and may not do
The model rewrites the structured facts it's given into a more natural investigator's paragraph. It must never receive raw post text, and it must never be given any ability to alter, add to, or contradict the confidence value or evidence list it was handed — its entire job is prose, not judgment. This is the concrete basis for the claim "the LLM never decides an attribution, it only phrases one the deterministic pipeline already computed" — a claim that's only true if the function signature genuinely enforces it, not just if the prompt text asks the model nicely to behave.

### 3. Silent, complete fallback
If Ollama isn't running, isn't reachable, or the configured model isn't pulled locally, the caller must receive the Prompt 10 template output with **no visible error, no broken UI state, and no user-facing indication that anything failed** — from the end user's perspective, the system should look identical whether the polish layer succeeded or was skipped. A model-download failure or a server that wasn't started before the demo must never be able to break anything downstream of this module.

## Explicit constraints & known gotchas
- Do not stand up a second `ChatOllama` configuration or a second `llm_model` config key — reuse Prompt 15's exactly.
- Do not let this module import or access anything from `src/ingest/` or `posts` directly — its only input is the structured dictionary from Prompt 10, and enforcing that at the function-signature level (not just by convention) is what makes the "never hallucinates a new fact" claim checkable.
- Do not surface an "LLM unavailable" message, warning banner, or degraded-mode indicator anywhere in the UI — the fallback needs to be genuinely invisible, not visibly-degraded.

## Definition of Done
- [ ] With Ollama running and the configured model pulled, generate LLM-polished explanations for the same set of pairs used in Prompt 10's Definition of Done, and confirm each one reads as a natural paragraph while containing no fact absent from the structured dictionary it was given — do this comparison explicitly, sentence-claim by sentence-claim, for at least 2 examples.
- [ ] Confirm, by inspecting the actual function signature/call (not a comment claiming it), that this module's only input is the structured evidence dictionary — no raw post text, no direct database access.
- [ ] Stop Ollama (or point the config at an unreachable endpoint) and confirm the caller receives the exact Prompt 10 template output, with no error surfaced anywhere the end user would see it.
- [ ] Confirm this module reuses the identical `llm_model` config value already used by Prompt 15's agent — not a second, independently-configured model.
- [ ] Run the investigator agent (Prompt 15) and the explanation-polish path in the same session and confirm memory usage stays reasonable — i.e., confirm you are not accidentally loading two separate model instances.

## Required tests
- A test asserting that when the LLM endpoint is unreachable (mocked or pointed at an invalid address), the function returns exactly the Prompt 10 template output, not an exception, not an empty string, and not a partially-rewritten result.
- A test asserting the rewrite function's signature/interface only accepts the structured evidence dictionary type — not a raw post, not a database handle — so a future change can't accidentally widen its access without the test failing first.

## Do not
- Do not configure a second local model.
- Do not give this module any path to raw post text or direct database access.
- Do not surface any degraded-mode indication to the end user when falling back to templates.

## Report back
Report the sentence-claim-level comparison for at least 2 polished examples against their source data, the function-signature/input-scope confirmation, the Ollama-down fallback confirmation, the shared-model-config confirmation, the combined-session memory check, and both test results.
