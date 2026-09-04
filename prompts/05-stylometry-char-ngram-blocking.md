# Prompt 05 — Stylometry channel 1: character n-grams, text hygiene, and blocking

## Objective
Build the style-based similarity channel — the one that's supposed to catch "same person, different topic" rather than "different people, same topic" — and the candidate-pair blocking step that makes scoring tractable at corpus scale. This prompt also implements the mandatory text-hygiene and alias-redaction steps that make every claim in Prompt 04 and Prompt 11 actually true rather than aspirational.

## Spec references
`SPEC.md` §8.1 (char n-grams), §8.3 (blocking), §8.4 (text hygiene and redaction — read this subsection especially carefully, it has the most consequential correctness requirement in the stylometry section).

## Preconditions
Prompts 01–04 complete: full corpus ingested, evidence extracted, label set built.

## Detailed requirements

### 1. Text hygiene — `src/stylometry/` shared preprocessing, applied before any vectorization
Before any post body is fed to a vectorizer (this prompt's char n-grams, and Prompt 06's embeddings), strip:
- Quoted text (content inside `div.quote` or equivalent quote markup) — if alias A quotes alias B, both documents now contain B's words, and any similarity model will "discover" a false match. This is the single most direct route to a stylometric false positive in this corpus, and it must be removed, not down-weighted.
- Signature blocks and PGP armor blocks.
- URLs.
- Market boilerplate (repeated forum chrome text that isn't actually the poster's writing).

### 2. Alias redaction — mandatory, and stronger than just dropping the label column
Per `SPEC.md` §8.4: removing the username from the pair's *label* is not sufficient, because the handle frequently appears **inside the post body itself** (signature lines like "- AngelEyes") and inside PGP UIDs ("AngelEyes <...>"). Before vectorizing an alias's document for evaluation, redact:
- The exact alias string, case-insensitively.
- Near-variants: with underscores/hyphens inserted or removed, with a trailing digit suffix stripped, and common leetspeak substitutions (e.g., a handle containing letter/digit look-alike swaps).

Without this, the char n-gram model isn't measuring writing style — it's reading the handle out of the text and matching a string, which is exactly the "circular" accusation the spec anticipates a judge raising (§11.2, §22 risk row). This redaction must be applied specifically at **evaluation time** (when scoring labeled pairs) — the production/unlabeled path also benefits from it but the mandatory case is anywhere a `label` is present, since that's where the blind-protocol claim has to hold.

### 3. `src/stylometry/char_ngram.py`
- Fit a character-level TF-IDF vectorizer over the whole corpus using word-boundary-aware character n-grams in the 3–5 length range, sublinear term frequency scaling, a minimum document frequency floor (the spec suggests 3), and a feature cap (the spec suggests 200,000) to keep the vocabulary tractable.
- Build one document per alias by concatenating all of that alias's (hygiene-cleaned, and where applicable redacted) post bodies.
- `S_char(A, B)` = cosine similarity between alias A's and alias B's TF-IDF vectors.
- Document in the module why character n-grams are the workhorse here: punctuation habits, spacing quirks, casing, and typo patterns are topic-independent, which is exactly what keeps this channel from just re-discovering "these two vendors both sell cannabis."

### 4. Blocking — `src/stylometry/` (or a dedicated `blocking.py`)
Corpus-scale pairwise scoring is not feasible (the spec's own math: 50k aliases → 1.25 billion pairs). Build a FAISS `IndexFlatIP` over the char n-gram vectors reduced to a lower dimensionality via `TruncatedSVD` (the spec suggests 256 dimensions), and retrieve the top-50 nearest neighbors per alias as candidates.
- **Force-include** every alias pair that already shares any hard evidence from Prompt 03's `evidence` table, regardless of whether they'd otherwise make the top-50 neighbor cut — these are exactly the pairs that matter most, and stylometric blocking alone might miss them.
- The final candidate set for downstream scoring is the union of: top-50-neighbor pairs, hard-evidence pairs, and every labeled pair from Prompt 04 (so the eval set is guaranteed scoreable).

### 5. Report blocking recall honestly, in both forms
Compute and report **two separate numbers**, not one:
- The recall you'd naively report given the candidate set as constructed (which is inflated, because eval pairs were force-included).
- The **honest** number: of the labeled positive pairs, what fraction would have survived the top-50-neighbor cut *without* the forced inclusion of evidence/eval pairs. This is the number that actually answers "would this blocking strategy work in production, on pairs you don't already know are positive," and the spec is explicit that failing to report it separately hides a real limitation behind a misleadingly good headline number.

## Explicit constraints & known gotchas
- Redaction is easy to implement in a way that looks right but doesn't actually fire on the cases that matter (a PGP UID embedding the handle, a leetspeak variant). It needs its own dedicated test — see below — not just an assumption that "the redact function exists so it's handled."
- Do not skip text hygiene "since it's just cleanup" — the quoted-text leak specifically is a known, documented failure mode in this exact kind of forum corpus, called out explicitly in the spec.
- Fit the TF-IDF vectorizer on the full corpus, not per-market — cross-market comparability is the entire point of this channel.

## Definition of Done
- [ ] Report the fitted vocabulary size (post-`max_features` cap) and confirm it's within the configured cap.
- [ ] Compute `S_char` for a hand-picked pair you expect to be similar (e.g., two posts you can see by eye are from the same person's writing style, if such a pair is identifiable in your labeled positives) and a pair you expect to be dissimilar, and confirm the scores go the expected direction.
- [ ] Report the blocking candidate-set size (top-50-neighbor pairs ∪ hard-evidence pairs ∪ eval pairs) compared to the full N² pair count it's replacing — the reduction should be dramatic (many orders of magnitude).
- [ ] Report **both** blocking recall numbers (with forced inclusion, and without it) — not just one.
- [ ] Text hygiene is verified by picking one post that contains a quote block and confirming the quoted portion is absent from the hygiene-cleaned text used for vectorization.

## Required tests
- `tests/test_redaction.py` — construct (or use a real) post signed `"- AngelEyes"` and a PGP UID string containing the handle `"AngelEyes"`, run redaction, and assert the handle is absent from both outputs, including at least one near-variant case (e.g., `"Angel_Eyes"` or a leetspeak substitution). This test is explicitly called out in the spec as currently missing evidence for a claim made on stage — treat it as load-bearing, not routine.
- A test confirming the blocking candidate generator correctly force-includes a synthetic pair that shares hard evidence but would rank outside the top-50 neighbors on stylometric similarity alone.

## Do not
- Do not report only the inflated (forced-inclusion) blocking recall number without also reporting the honest one.
- Do not skip alias redaction for any pair that carries a `label` — this is where the blind-protocol claim either holds or doesn't.

## Report back
Report vocabulary size, the sanity-check pair scores, both blocking recall figures, the text-hygiene spot-check, and both test results.
