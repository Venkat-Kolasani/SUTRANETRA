# Prompt 12 — Edge-case evaluation tests and the ethics document

## Objective
Produce the three specific edge-case results the spec earmarks as individual demo slides, and the ethics statement that's a required deliverable rather than optional framing copy. This prompt is evidence-of-rigor work: its entire purpose is giving you (and later, a judge) concrete proof that the system fails correctly on the cases that matter, not just that it succeeds on the easy ones.

## Spec references
`SPEC.md` §11.4 (the three edge cases), §2 (legal/ethical scope — this is the content basis for `docs/ethics.md`).

## Preconditions
Prompt 07 (fusion model and evaluation) and Prompt 09 (opsec) complete.

## Detailed requirements

### 1. Edge case 1 — the hard-negative rejection
Identify or construct a pair meeting all three conditions: two vendor aliases, same market, same product category, similar register/topic (so a topic-only signal would score them high), and **no shared hard evidence**. Run it through the full fusion pipeline and confirm the resulting confidence is low — correctly *not* linked. Document this as its own result, with the actual confidence number and the actual per-feature scores that produced it. The spec is explicit that this correct rejection is stronger evidence of rigor than any successful match — a system that finds everything is not impressive, a system that also correctly declines to find things that aren't there is.

### 2. Edge case 2 — sparse evidence
Identify or construct an alias with fewer than 10 posts. Confirm the system returns a low confidence for any pair involving it, with a reason indicating insufficient data (this should route through the same low-post-count handling logic that Prompt 06's `<20 timestamped posts` rule established for the temporal feature, extended here to the pair-level confidence/reason output generally) — and confirm it never returns a forced, artificially confident match just because a pair happens to exist in the candidate set.

### 3. Edge case 3 — adversarial paraphrase
Take one real alias's posts, machine-paraphrase roughly half of them (any reasonable method — a local paraphrasing tool or model is fine, this doesn't need to be sophisticated), and treat the paraphrased half as a synthetic second alias. Run the pair through the pipeline and report:
- How much `S_char` degrades between the real alias and its paraphrased half, compared to `S_char` for the same alias against itself pre-paraphrase (or against a genuinely different alias, as a baseline).
- Whether `S_hard` (if the original posts carried any hard evidence) still carries the link even as the stylometric signal degrades.

This is the honest, demonstrable answer to "what happens if an actor changes how they write" — and it should show a real limitation (stylometry does degrade under paraphrase) alongside a real strength (hard evidence doesn't), rather than overclaiming robustness the system doesn't actually have.

### 4. `docs/ethics.md`
Write the ethics statement based on `SPEC.md` §2, in your own words rather than copied verbatim, covering: no interaction with any live criminal infrastructure at any point in the build; the historical/public nature of the corpus and its standing as an established research dataset in this field; the fact that the only hidden service ever scanned is the team's own, deliberately misconfigured for the demo; the public-by-design nature of Certificate Transparency data; the intended law-enforcement-attribution use case; and the explicit framing that wallets/fingerprints/handles are reported as pseudonymous identifiers with a confidence score, never as identity verdicts.

## Explicit constraints & known gotchas
- Do not skip any of the three edge cases because the "happy path" evaluation from Prompt 07 already looks good — a strong PR-AUC number does not substitute for demonstrated correct-rejection behavior, and a judge asking "what about X" with no prepared answer is a materially worse outcome than having gone through the work now.
- The adversarial-paraphrase case is expected to show *some* degradation — do not tune anything to make this case look artificially clean. A believable, moderate degradation with hard evidence still holding is a more credible result than a suspiciously perfect one.
- `docs/ethics.md` should read as a genuine operating statement, not marketing copy — factual, specific, and matching what the system actually does (don't claim protections the implementation doesn't actually enforce).

## Definition of Done
- [ ] Report the hard-negative case: the two aliases involved, why they'd be expected to look similar on a topic-only model, the actual per-feature scores, and the actual fused confidence — confirmed below whatever threshold you're using for a positive link.
- [ ] Report the sparse-evidence case: the alias, its post count, the resulting confidence and reason string for at least one pair involving it.
- [ ] Report the adversarial-paraphrase case: the pre- and post-paraphrase `S_char` values, whether `S_hard` held steady, and a one-paragraph interpretation of what this demonstrates and what it doesn't.
- [ ] `docs/ethics.md` exists, is written in your own words, and covers all six points from `SPEC.md` §2.

## Required tests
- A test asserting the hard-negative synthetic/identified pair scores below the configured link threshold.
- A test asserting an alias with fewer than 10 posts never produces a fused confidence above a low ceiling you define (e.g., confirm the sparse-data path is actually enforced in code, not just true by coincidence for the one example you checked by hand).

## Do not
- Do not skip any of the three edge cases.
- Do not tune the paraphrase case's outcome — report what actually happens.
- Do not write `docs/ethics.md` as promotional language disconnected from what the system actually enforces.

## Report back
Report all three edge-case results with actual numbers, confirm `docs/ethics.md` is written and covers all six required points, and report both test results.
