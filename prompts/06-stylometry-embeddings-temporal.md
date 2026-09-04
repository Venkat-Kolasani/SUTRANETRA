# Prompt 06 — Stylometry channel 2 (embeddings) and temporal features

## Objective
Add the semantic/topic similarity channel and the posting-time channel, both feeding into the fusion model in Prompt 07. This prompt is explicit that the embedding channel is a *topic* signal, not a style signal — conflating the two is exactly the mistake the spec's own first draft made, producing the false-positive pattern where two unrelated cannabis vendors score high just because they discuss the same product.

## Spec references
`SPEC.md` §8.2 (embeddings), §8.4 (hygiene/redaction — reuse from Prompt 05, apply identically here), §9 (temporal).

## Preconditions
Prompts 01–05 complete, including the shared text-hygiene and redaction functions built in Prompt 05 — this prompt reuses them, it does not reimplement them.

## Detailed requirements

### 1. `src/stylometry/embed.py`
- Use `sentence-transformers/all-MiniLM-L6-v2` on CPU, batching (batch size 64) for throughput.
- Cap the number of posts embedded per alias (the spec suggests 200, sampled) — char n-grams run over everything since they're cheap, but the embedding pass does not need to, and capping keeps runtime sane on the full corpus without materially hurting the topic signal, since topic is a fairly stable property across an alias's posts.
- Embed each (hygiene-cleaned, redacted where applicable) post individually, then mean-pool per alias to get one vector per alias.
- `S_embed(A, B)` = cosine similarity between the two alias-level mean-pooled vectors.
- Document explicitly, in the module and in whatever report references this score, that `S_embed` is a **topic/domain proximity signal**, not a style signal, and should never be presented as evidence of writing-style similarity — that mislabeling is precisely what produced the rejected first-draft approach.

### 2. `src/temporal/activity.py`
- Build a 24-bin hour-of-day histogram and a 7-bin day-of-week histogram per alias, normalized to sum to 1, using only posts with a non-null `ts`.
- `S_time(A, B) = 1 − JensenShannon(hist_A, hist_B)` computed on the hour-of-day histograms (the day-of-week histogram can inform the timezone estimate below or be reported separately, but the core `S_time` feature the spec defines is the hour-of-day Jensen-Shannon comparison).
- **Timezone estimate**: compute the circular mean of an alias's posting hours, derive an implied UTC offset, and map it to a small set of candidate regions. Report this as a weak, explicitly-labeled indicator with a stated confidence — never as a location claim. This is a genuine step toward the "real-world identity" framing the PS asks for, and it's cheap to compute, but it must never be presented more confidently than it deserves.
- **Missing-data handling**: for any alias with fewer than 20 timestamped posts, set `S_time = NULL` rather than computing a low-confidence number that looks precise. The fusion model (Prompt 07) needs to handle this explicitly — impute to the corpus mean and add a separate binary `time_missing` indicator feature, rather than silently defaulting to 0 or some other value that would bias the model.

## Explicit constraints & known gotchas
- Reuse Prompt 05's hygiene/redaction pipeline exactly — do not write a second, slightly different cleaning pass for this module. Divergent preprocessing between the two stylometry channels would make their scores non-comparable in ways that are hard to debug later.
- The embedding pass is the slowest step in the pipeline so far. If it's too slow on the full corpus even with the per-alias post cap, that's a capacity problem to solve within the cap/batching approach already specified (e.g., confirm batching is actually being used, confirm you're not accidentally re-loading the model per call) — not a reason to skip hygiene or redaction to save time elsewhere.
- Do not let a missing timezone estimate (e.g., an alias with too few timestamped posts) block the rest of that alias's scoring — it's one weak indicator among several, not a required field.

## Definition of Done
- [ ] Report embedding computation time for the full corpus (or a representative large subset) and confirm it completed in a reasonable window given the per-alias post cap and batching.
- [ ] Compute `S_embed` for the same sanity-check pairs used in Prompt 05 and confirm the topic-similarity behavior is distinguishable from the style-similarity behavior — specifically, find or construct a pair that is topically similar (same product category) but stylistically different, and confirm `S_embed` is high while `S_char` (from Prompt 05) is comparatively low for that same pair. This is the concrete proof that the two-channel design is actually doing its job.
- [ ] Report `S_time` for at least 3 alias pairs with sufficient timestamped posts, and confirm the NULL/missing-data path fires correctly for at least one alias with fewer than 20 timestamped posts.
- [ ] Report the timezone estimate for at least 2 aliases with strong posting-hour concentration, worded as a weak indicator with stated confidence, not a location claim.

## Required tests
- A test confirming the embedding channel and the char n-gram channel diverge on the topically-similar/stylistically-different pair identified above — this is the direct evidence that the two-channel design (the plan's own fix over its rejected single-model first draft) actually holds in this implementation, not just in theory.
- A test confirming `S_time` is `NULL` (or the designated missing-value sentinel) for an alias with fewer than 20 timestamped posts, and is a real computed value for one with more.

## Do not
- Do not reimplement text hygiene or redaction separately from Prompt 05's version.
- Do not present `S_embed` as a style/writing signal anywhere in code comments, UI copy, or the eventual report template.
- Do not silently default missing `S_time` to 0 — that's a specific numeric claim ("posting patterns are maximally different"), not an absence of data, and it will bias the fusion model if treated as a real observation.

## Report back
Report embedding runtime, the topic-vs-style divergence evidence, `S_time` sample outputs including the missing-data case, the timezone estimate examples, and both test results.
