---
name: validation-and-novelty
status: reviewed 03 Sep 2026
verdict: PROCEED — build as specified, with the adjustments in §4
---

# Validation & Novelty Assessment — SIH26151 / SUTRANETRA

**Product name:** SUTRANETRA (*sutra* = thread/connection, *netra* = eye/vision) — *"The eye that follows the hidden threads."*  
(Build-kit folder may still be named `darkattrib-buildkit`; judge-facing brand is SUTRANETRA.)

This is an independent check of `SPEC.md`, not a re-statement of it. Every claim below was checked against a live source on 03 Sep 2026. Where I disagree with the spec or found a gap it doesn't cover, that's flagged explicitly in §4 — this document is not a rubber stamp.

## 1. Problem statement — confirmed real

SIH26151, National Technical Research Organisation (NTRO), "Dark web threat actor de-anonymization," theme **Blockchain & Cybersecurity**, type **Software**, is a listed problem statement in the official Smart India Hackathon 2026 catalogue, deadline 20 September 2026. This matches the spec's header exactly — organisation, theme, type, and deadline all check out against the published SIH 2026 problem statement list. The PS is real and current, not a stale or misremembered one.

## 2. Data source — confirmed real and correctly characterized

The **Darknet Market Archives (dnmarchives)**, compiled by Gwern Branwen et al., is a genuine, long-standing, publicly hosted dataset on archive.org covering ~89 Tor/Bitcoin darknet markets and forums, 2011–2015 (Silk Road, Agora, Evolution, and others). It is CC0-licensed, has no signup or authentication gate, and is cited as the standard corpus in multiple peer-reviewed studies of darknet markets, replication studies, and darknet-forum NLP datasets (e.g. the `darkweb_clearweb_darktopics` corpus explicitly builds on it). This directly supports the spec's central data-acquisition decision: it's real, it's public, and it's the field's de facto standard, not an obscure or dead link.

I did not re-download and byte-verify each individual `.tar.xz` filename or the exact HTML selector map in §6 — that would require actually fetching multi-hundred-MB archives, which is squarely the agent's job at Step 0/1, not a pre-build validation task. Treat the selector map as the spec's own claim, to be confirmed empirically the moment `cannabisroad3-forums.tar.xz` is parsed (this is already baked into Prompt 01's Definition of Done).

## 3. Certificate Transparency pivot — confirmed real, one caveat added

The Cert Spotter (`api.certspotter.com/v1/issuances`) endpoint, request shape (`domain`, `include_subdomains`, `expand=dns_names`, `expand=issuer`), and response fields (`id`, `dns_names[]`, `pubkey_sha256`, `not_before`/`not_after`) all match SSLMate's own current API reference exactly.

**One thing the spec underweights:** SSLMate's current documentation shows unauthenticated requests are increasingly steered toward an API key/Bearer token (`sslmate.com/signup?for=certspotter_api`) for anything beyond light, occasional use. The spec already treats crt.sh as a fallback and mandates aggressive response caching (§12.2) — that's the right mitigation — but Prompt 09 below adds an explicit instruction to register a free Cert Spotter account key early and keep it optional/env-var-gated, rather than discovering an unauthenticated rate-limit wall during the ingest-heavy final week.

LangChain/LangGraph reaching a stable 1.0 line, and both frameworks continuing frequent point releases through mid-2026, is independently confirmed. I could not byte-verify the exact patch numbers `langgraph==1.2.11` / `langchain==1.3.17` — both projects release multiple times a week, so any pin is stale within days. This doesn't invalidate the spec: §16 already tells the builder to re-check `pip index versions` and inspect `dir()` on the installed package before writing agent code instead of trusting a blog post. That instruction is correct and is preserved verbatim as a hard requirement in Prompt 13/15 below.

## 4. Where I disagree with, or would add to, the plan

The plan is unusually rigorous for a hackathon spec — it already self-corrects most of the mistakes teams actually make (synthetic ground truth, hand-tuned fusion weights, framework-owns-the-logic coupling, no blind eval). My additions are these:

- **Time budget is the real risk, not technique.** Sixteen build steps, a 1M+-post ingest, a two-channel stylometry pipeline, a learned fusion model, two orchestration frameworks, an optional graph database, and a Tor hidden service is 2–3 weeks of focused solo work, not a weekend. The spec's own §21 ("Do NOT build") and step ordering already protect the critical path, but nothing in the original doc states a **hard internal deadline per phase**. `CLAUDE.md` below adds a stop condition: if Step 9 (opsec) isn't complete with time to spare before the pitch deadline, the team drops everything after it before dropping anything before it — this is stated in the plan's prose (§17) but not enforced anywhere structurally. I've made it a rule.
- **The "novelty" claim needs one caveat spoken on stage, not just believed internally.** Alias correlation via stylometry (char n-grams + embeddings + graph clustering) is a well-studied academic technique — it is not itself new. What's comparatively rare in a hackathon submission is (a) treating it as one signal fused with hard cryptographic/PGP/wallet evidence into a *calibrated* probability instead of a hand-tuned score, and (b) actually building capability #1 (infrastructure leak → CT pivot → real-world artifact) instead of stopping at pseudonym correlation, which is what most teams will submit because it's the "safe," NLP-only interpretation of "de-anonymization." That combination — and specifically shipping a working leak scanner against a self-hosted onion service — is the genuinely differentiating claim, and it's a defensible one. Say exactly that on stage; don't claim the stylometry itself is novel.
- **The blind-eval protocol (§11.2) is the plan's single best defensive move.** It's rare for a student team to strip the label from the evaluation input before scoring. Keep it in the pitch verbatim — it preempts the most common "gotcha" question a technical judge asks about any correlation system.
- **Formalize a third layer beyond correlation → attribution.** The original plan framed two halves well; the architecture is stronger as **Correlation → Attribution → Evidence / Investigation**. The third layer answers: why should an investigator believe this, what exactly was observed, and what should they investigate next (`explain/`, UI/exports, agent, Cypher). Adopted into `SPEC.md` §1 / §3 / §14 and the agent contracts (`AGENTS.md`, `CLAUDE.md`).
- **Add immutable post source lineage + an explicit `cases` table.** Provenance must walk `cluster → pair → evidence → post → archive member`. Cases make runs look like investigations (corpus snapshot, config hash, model version, threshold) rather than one-shot scripts. Adopted in `SPEC.md` §6.1 / §6.2; prompts 00–02, 07–09, 11, 13, 15 updated with tests (`test_post_provenance`, `test_cases`).
- **Ship an Evidence Trail tab.** Vertical ordered chain (alias → post → PGP/wallet → peer → confidence → clearnet → CT → sibling domain) is the best single UI answer to "how did you reach this?" Adopted in `SPEC.md` §15 / §14 / §19; Prompt 10 builds `explain/trail.py`; Prompt 11 renders the tab; `test_evidence_trail.py` required. Never invent missing OpSec/CT steps.

## 5. Verdict

Build it as specified. The data source is real, the CT-pivot API is real and correctly shaped, the problem statement is real and current, and the architectural decisions in §0 of the spec (deterministic core, framework-as-wrapper, learned fusion, blind eval) are sound engineering, not hackathon theater. The prompt kit that follows builds it in the order the spec itself lays out in §17, with a Definition of Done and required tests attached to every step so you always know whether a given prompt actually landed before moving to the next one.
