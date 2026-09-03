# Prompt 07 — Fusion model, cases, and evaluation (project midpoint)

## Objective
Combine the four signal channels built so far (hard evidence, char n-grams, embeddings, temporal) into one learned, calibrated confidence score per alias pair, **scoped to an explicit investigation case**, and produce the first real, honest performance number for the whole system. The spec calls this the project's midpoint for a reason: everything before this step builds signals, and everything after it consumes this score. Getting the fitting protocol and case ledger right here is what makes every later demo claim defensible and repeatable.

## Spec references
`SPEC.md` §6.2 (cases), §10 (fusion), §11.1–§11.3, §11.5 (evaluation and reporting — §11.4's edge-case tests are deferred to Prompt 12, not built here).

## Preconditions
Prompts 01–06 complete: `S_hard`, `S_char`, `S_embed`, `S_time` all computable for the blocked candidate pair set, and the labeled pair set from Prompt 04 available. Schema from Prompt 00 includes `cases` and case-scoped `pair_scores`.

## Detailed requirements

### 1. `src/pipeline/case.py`
Implement create / open / complete for investigation runs:
- Mint or accept a `case_id` (e.g. `CASE-2026-001` or `CASE-YYYYMMDD-HHMMSS`).
- Persist `created_at`, `corpus_snapshot` (JSON: markets, n_posts, n_aliases), `config_hash` (sha256 of canonical scoring-relevant config — **not** machine-local absolute paths), `model_version` (label + optional short hash of the persisted model file), `threshold`, `status` (`created` → `running` → `complete` | `failed`).
- Never overwrite another case's result rows.

### 2. `src/fusion/features.py`
For every candidate pair (from Prompt 05's blocking output), assemble the five-element feature vector: `S_char`, `S_embed`, `S_hard`, `S_time` (with the missing-value handling from Prompt 06 — impute to corpus mean plus a `time_missing` indicator, not a raw NULL passed into the model), and `log1p(n_shared_hard)` (the raw shared-hard-evidence count, log-transformed, alongside the already-saturating `S_hard` score — the spec includes both because they carry slightly different information: one is the saturating strength, one is the raw count).

### 3. `src/fusion/model.py`
- Fit a `LogisticRegression` with `class_weight='balanced'` and `C=1.0` on the five-feature vectors, using the labeled pairs from Prompt 04.
- **Split by alias, not by pair, before fitting.** Every alias that appears in any training pair must not appear in any pair used for held-out evaluation. This is not a minor detail — splitting by pair instead of by alias lets the same alias appear on both sides of the split, and the model ends up memorizing that specific alias's writing style rather than learning a general notion of "when are two documents the same author." This exact mistake is the first thing a machine-learning-literate judge will probe for after asking about your baseline, and the spec calls out that VeriDark (an academic benchmark in this space) uses disjoint author sets for precisely this reason.
- The model's output must be a **calibrated probability**, not a raw score — this is what lets an investigator meaningfully threshold on it later (e.g., "show me everything above 0.8").
- Persist the fitted model (coefficients and any fitted transformers) so it doesn't need refitting on every run; record `model_version` on the active case.
- Print the fitted coefficients somewhere visible (log output, a small report) — the spec is explicit that these coefficients are the actual, defensible answer to "why is hard evidence weighted more than stylometry," replacing what would otherwise be an indefensible hand-picked number.
- Implement `--heuristic` as a fallback mode using fixed weights (`[0.25, 0.10, 0.45, 0.20]` against `[S_char, S_embed, S_hard, S_time]`, per the spec) for use **only** if the labeled set proves too small to fit reliably. If you use this fallback, it must be labeled as a fallback everywhere its output is reported, not presented as the primary result.

### 4. Write scores under the active case
All `pair_scores` inserts must include `case_id`. Scoring CLI accepts `--case-id` (create via `case.py` if missing). Completing a successful score run sets case status appropriately (recommended: leave `running` until graph/opsec for that case finish in later prompts, or document `complete` after fusion if those stages are optional for this case — pick one convention and stick to it).

### 5. `src/fusion/evaluate.py`
On the held-out (alias-disjoint) evaluation split:
- Compute precision, recall, F1, and **PR-AUC** — the spec is explicit that plain accuracy is meaningless here because the classes are wildly imbalanced (almost no candidate pair is actually a true match), and a model that finds nothing at all can still score 99.9% accuracy while being useless.
- Generate a PR curve plot and a confusion matrix at whatever threshold you choose to report as the operating point, and save both as files that get committed to the repo (not regenerated only in-memory) — the spec is explicit that judges ask for numbers and you need the file open and ready, not regenerated live under time pressure.

## Explicit constraints & known gotchas
- Alias-disjoint splitting is the single most important correctness requirement in this prompt. Verify it programmatically (see Definition of Done below), not just by writing code you believe does it correctly.
- Do not report accuracy as a headline metric anywhere. PR-AUC is the number that means something given the class imbalance here.
- The `--heuristic` fallback exists for a real contingency, not as an easier default path — use the learned model unless the labeled set genuinely can't support fitting five coefficients reliably (a very small positive count, per Prompt 04's own reporting).
- Two cases with different thresholds must be able to coexist without clobbering each other's `pair_scores`.

## Definition of Done
- [ ] Create at least one real case row (report `case_id`, corpus snapshot, config_hash, model_version, threshold, status).
- [ ] Programmatically verify the train/test split is alias-disjoint: the set of aliases appearing in any training pair and the set of aliases appearing in any evaluation pair have empty intersection. Report this check's actual result, not just that the split code "should" do it.
- [ ] Report the fitted logistic regression coefficients for all five features, and give a one-sentence interpretation of the relative weights (e.g., which signal dominates and whether that matches intuition — hard evidence should weight heavily given its saturating design).
- [ ] Report precision, recall, F1, and PR-AUC on the held-out split, with the actual numbers, not placeholders.
- [ ] Confirm the PR curve PNG and confusion matrix files exist in the repo and open correctly.
- [ ] Confirm all written `pair_scores` rows carry the active `case_id`, and a second case with a different threshold can be created without deleting the first case's rows.
- [ ] Run the `--heuristic` fallback path once even if it's not the primary mode, and confirm it produces a working (if less accurate) confidence score — this path needs to work even if you don't end up using it, since it's the documented contingency if the labeled set thins out later.

## Required tests
- `tests/test_fusion.py` — construct one synthetic feature vector representing "shared PGP fingerprint, nothing else strong" and confirm the fitted model's output confidence is above your chosen threshold; construct another representing "high topical similarity, zero hard evidence" and confirm its confidence stays below threshold. This directly tests the claim that hard evidence dominates and topic-only similarity does not manufacture a false match — the exact failure mode the spec's rejected first draft had.
- `tests/test_cases.py` — create two cases with different thresholds; assert pair_scores for case A are not visible when querying case B; status transitions work; identical canonical config yields identical `config_hash`.

## Do not
- Do not split by pair. Split by alias.
- Do not report accuracy as a headline number.
- Do not present the `--heuristic` fallback output as the primary result unless you've documented that the learned model genuinely couldn't be fit reliably, and said so explicitly wherever the confidence score is reported.
- Do not write `pair_scores` without a `case_id`.

## Report back
Report the case card fields, the alias-disjoint split verification result, the fitted coefficients with interpretation, the full metric set (precision/recall/F1/PR-AUC) with actual numbers, confirmation of the saved PR curve and confusion matrix files, the heuristic-fallback smoke test result, both test outcomes, and update `docs/build-log.md`.
