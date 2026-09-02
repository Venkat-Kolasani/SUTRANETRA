# Build log — SUTRANETRA (SIH26151)

Per-prompt progress, metrics, and issue notes for demos, judge Q&A, and interviews.
Agents must append a section after every `prompts/NN-name.md` run (pass or fail-stop).
Chat history is not a substitute for this file.

**Product:** SUTRANETRA — *"The eye that follows the hidden threads."* (*Sutra* = thread/connection · *Netra* = eye/vision)

## Entry template

Copy this block for each prompt:

```
### YYYY-MM-DD — prompts/NN-name.md

- **Status:** complete | blocked | partial
- **Profile:** dev | demo
- **What shipped:** …
- **DoD:** item → pass/fail (quote actual output where relevant)
- **Tests:** list → pass/fail
- **Metrics:** row counts, PR-AUC, findings, etc. (honest numbers)
- **Issues / near-misses:** errors, workarounds, degraded paths, open questions
- **Judge/interview notes:** one-liners that answer “why did you do X?” or “what broke?”
```

---

## Log

### 2026-09-03 — brand: SUTRANETRA (not a build prompt)

- **Status:** complete
- **What shipped:** Product name **SUTRANETRA** + tagline + etymology across `SPEC.md`, `AGENTS.md`, `CLAUDE.md`, Prompt 00 README requirement, demo open, validation/build-log headers. Shipped repo tree label `sutranetra/`; this build-kit folder may remain `darkattrib-buildkit`.
- **Judge/interview notes:** Name is Indian-rooted and maps to the product metaphor — following hidden threads (correlation/attribution) with an investigator's eye (Evidence Trail).
- **Issues / near-misses:** none.

### 2026-09-03 — plan: lineage + cases + Evidence Trail (not a build prompt)

- **Status:** complete (plan/prompt sync)
- **What shipped:** `SPEC.md` §6.1 source lineage, §6.2 cases, §15 Evidence Trail tab + `explain/trail.py`; demo §19; tests §18 (`test_post_provenance`, `test_cases`, `test_evidence_trail`). Prompts 00, 01, 02, 07, 08, 09, 10, 11, 13, 15 updated. `AGENTS.md` / `CLAUDE.md` correctness + cut-order updated.
- **Design notes:** Corpus (`posts`/`aliases`/`evidence`) shared; results (`pair_scores`/`clusters`/`opsec_findings`) case-scoped. `content_sha256` hashes UTF-8 `raw_html`. Trail never fabricates OpSec/CT steps.
- **Judge/interview notes:** Case card + Evidence Trail + archive-member lineage is the answer to "how / where / can you reproduce it?"
- **Issues / near-misses:** Prior schema omitted `raw_html` despite evidence extractors needing it — fixed in §6 schema as part of this pass.

### 2026-09-03 — plan framing update (not a build prompt)

- **Status:** complete
- **What shipped:** Formalized three-layer stack in `SPEC.md` §1/§3/§14 and synced `AGENTS.md` / `CLAUDE.md` / `docs/VALIDATION-AND-NOVELTY.md`.
- **Stack:** Correlation → Attribution → Evidence / Investigation.
- **Judge/interview notes:** Third layer is why-believe / what-observed / what-next — turns a calibrated score into an interrogable case file without changing the deterministic scoring path.
- **Issues / near-misses:** none — framing only; no code change.
