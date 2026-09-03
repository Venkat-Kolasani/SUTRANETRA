# Prompt 04 — Cross-market ground-truth label set

## Objective
Build the labeled pair set that Prompts 07 (fusion model fitting) and 11 (evaluation) both depend on, using a real, defensible ground-truth source rather than any planted or synthetic signal. Getting this step honest is what makes every metric reported afterward meaningful.

## Spec references
`SPEC.md` §11.1 (ground truth definition), §11.2 (the blind protocol this label set must support), §11.3 (the stated caveat), §22 risk row on thin same-username overlap.

## Preconditions
Prompts 01–03 complete: full corpus ingested, `aliases` populated across markets, `evidence` populated.

## Detailed requirements

### 1. Positive pairs
The label is: the same username string appears as an alias on two different markets. Query `aliases` for `(alias)` values that recur across ≥2 distinct `market` values, and generate one positive-labeled pair per distinct market-pair combination for each such alias. Store these in `pair_scores` (or a staging table feeding it) with `label = 1`.

### 2. Negative pairs
Two negative sources, both required:
- **Random cross-market negatives**: aliases from different markets, sampled at random, that do not share a username. These establish the baseline "obviously different people" case.
- **Hard negatives**: different aliases, *same market*, discussing the *same product category* (approximate this by shared thread/subforum topic terms, or by aliases that post heavily in the same threads) with no shared hard evidence. This is the specific case that a topic-only model gets wrong — the spec is explicit that this is where character n-grams need to outperform a purely semantic embedding model, and without hard negatives in the label set you cannot actually measure whether that's true.

### 3. If the positive set is thin
If same-username cross-market overlap turns out too sparse to fit a model reliably, add `thehub` as an additional overlap source if it isn't already ingested (it's specifically valuable here — vendors from every market cross-post there), and as a secondary fallback, consider same-market temporal-split pairs (the same alias's early-period posts vs. late-period posts, treated as weak positives) — but only as a fallback, and label these clearly differently from the primary same-username-cross-market positives so downstream evaluation code can distinguish label quality/source if needed.

### 4. The blind protocol starts here, not at scoring time
This label set will later be used by Prompt 07 to fit a model and by Prompt 11 to evaluate it. **The username string that generated a positive label must never be exposed to any feature-computation step downstream** — this prompt's job is only to produce the `(alias_a, market_a, alias_b, market_b, label)` tuples; Prompts 05–06's feature extraction must independently strip/redact those alias strings before vectorizing. Flag this dependency clearly in this module's own documentation so whoever builds Prompt 06's redaction doesn't miss it.

### 5. State the caveat where the label set is defined, not just in the pitch deck
Same handle across markets is a labeling heuristic, not proof of identity — handle-squatting and post-Silk-Road-1 impersonation are both documented phenomena in this space. Write this caveat directly into the module's docstring/comments and into whatever report or notebook documents the label set, exactly as the spec requires it be stated on stage (`SPEC.md` §11.3) — the goal is that nobody downstream can present this label set's positives as ground truth without also carrying the caveat.

## Explicit constraints & known gotchas
- Do not plant any synthetic positive pairs, ever, under any circumstance, even for "quick testing." The entire point of this step — and the thing that separates it from the plan's own rejected first draft — is that every positive label traces back to something that actually happened in the real corpus.
- Splitting by pair (train/test) instead of by alias is a data-leakage bug, but that's Prompt 07's concern at fitting time — this prompt's job is just to produce a clean, correctly labeled set with alias identity clearly recorded, so Prompt 07 *can* split by alias correctly. Make sure each labeled pair carries both aliases' identities in a form that supports grouping by alias later.

## Definition of Done
- [ ] Report the actual count of positive pairs found (same username, ≥2 markets) and the market pairs they span.
- [ ] Report the actual count of random cross-market negative pairs and hard-negative pairs generated.
- [ ] Confirm, by inspection of at least 5 positive pairs, that the underlying market/alias data genuinely supports the label (i.e., you can see the same alias string posting on both markets in the raw data, not just in a derived table you might have built incorrectly).
- [ ] Confirm, by inspection of at least 3 hard-negative pairs, that they are in fact same-market/same-topic/no-shared-evidence as intended, not accidentally something else.
- [ ] If the positive count is below what you judge sufficient to fit a 5-feature logistic regression reliably (a double-digit count is a red flag), document the decision to add `thehub` or temporal-split fallback pairs, and label the fallback pairs distinctly from primary positives.
- [ ] The caveat language from §11.3 is present in the module's own documentation, not only planned for the slide deck.

## Required tests
- A test asserting that a known, hand-verified positive pair (pick one real recurring alias from your corpus) is present in the generated label set with `label = 1`.
- A test asserting that the hard-negative generator never emits a pair that actually shares hard evidence (cross-check against the `evidence` table) — a "hard negative" that secretly shares a PGP fingerprint is a labeling bug, not a hard negative.

## Do not
- Do not plant synthetic positives.
- Do not let this module leak the alias string into any feature-computation code path — it only produces labels, it does not vectorize text.

## Report back
Report the actual positive/negative/hard-negative counts, the fallback-source decision (used or not, and why), the manual verification results for positives and hard negatives, and both test results.
