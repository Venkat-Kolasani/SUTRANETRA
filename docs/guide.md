# SUTRANETRA — Full Project Study Guide

*"Sutra" = thread/connection, "Netra" = eye/vision — "The eye that follows the hidden threads."*

SIH26151 · NTRO · Theme: Blockchain & Cybersecurity · Prototype for Dark Web Threat Actor De-anonymization

This document is written for study/presentation purposes: what the real-world problem is, what we built, why it's built that way, and the actual numbers produced by the real system — not a marketing summary.

---

## 1. The real-world problem

Dark-web marketplace vendors and buyers operate under throwaway pseudonyms (aliases/handles). When a marketplace shuts down or gets seized, the same actor typically **re-appears on a different marketplace under a new handle** — this is called re-branding or migration. Law enforcement and intelligence agencies (like NTRO) lose the trail every time this happens, because:

1. **There's no single system that connects a pseudonym across markets to (a) other pseudonyms of the same actor, and (b) any real-world infrastructure that actor leaks** (a server, a domain, a hosting account).
2. Analysts today do this manually — reading forum posts, cross-referencing wallet addresses by hand, guessing at writing-style similarity. It doesn't scale past a handful of markets and doesn't produce anything a court or an investigator can audit.
3. Most "dark web AI" proposals stop at capability #2 below (alias correlation) and call it de-anonymization. It isn't — correlating two pseudonyms tells you they're *probably* the same actor, not who that actor *is* or what real infrastructure they control.

**NTRO's problem statement literally asks for three things**, and a submission that only does the first is the generic version this spec was written to beat:

| # | What NTRO asked for | Why it's hard |
|---|---|---|
| 1 | Detect misconfigurations in Tor hidden services (exposed pages, certs linked to clearnet domains) | This is the only capability that produces a **real-world artifact** (an actual domain/IP), not just a probability. Almost nobody builds it because it sounds legally risky. |
| 2 | Map actors across marketplaces — handles, crypto keys, wallets, trust relationships | Needs real evidence extraction + graph construction, not just eyeballing forum text. |
| 3 | AI attribution of rebranded/migrated personas — writing style + behaviour | Needs a stylometric model that's robust to *what* someone is selling (topic) vs *how* they write (style) — most naive approaches confuse the two. |

---

## 2. The concept — how SUTRANETRA solves it

SUTRANETRA is built as **three layers stacked on top of each other**, because a score without a case file is useless to an investigator, and a case file without a real-world lead is just a research paper:

```
Layer 3: EVIDENCE / INVESTIGATION  <- "why should I believe this, what do I do next?"
         (Evidence Trail, UI, read-only investigator agent, Neo4j Cypher, case management)
              ^
Layer 2: ATTRIBUTION               <- "does this actor leak real infrastructure?"
         (OpSec misconfig scanner + Certificate Transparency log pivoting)
              ^
Layer 1: CORRELATION               <- "which pseudonyms are probably the same actor?"
         (stylometry + hard evidence + graph clustering, fused by a learned model)
```

**The framing that matters for the pitch:** Layer 1 alone produces *correlation between pseudonyms*. Layer 2 produces a *real-world artifact* — a clearnet domain, an IP, a hosting provider, something an investigator can actually go serve a warrant against. Layer 3 is what makes any of it usable as evidence rather than a black-box number.

### 2.1 How Layer 1 (correlation) actually works

Two aliases might be the same person because they:
- **Share hard evidence** — the literal same PGP key, Bitcoin address, onion address, or clearnet domain appears in both aliases' posts. This is the strongest signal (it's not a guess, it's a shared secret/identifier).
- **Write similarly** — character-level habits (punctuation, spacing, typos, casing) captured via TF-IDF on character n-grams. This is topic-independent — two vendors who both sell cannabis won't look similar on this channel unless they *write* similarly.
- **Talk about similar things** — sentence embeddings (MiniLM) capture topic/domain similarity. Two accounts both discussing "shipping stealth" will score close here — this channel exists to be reported separately from style, precisely so nobody can claim "the AI found matches" when it actually just found two people selling the same product.
- **Post at similar hours** — a posting-hour histogram gives a weak but real signal (and a timezone hypothesis) — someone posting 9am-5pm UTC+1 vs someone posting 2am-10am UTC+1 are unlikely to be the same person, all else equal.

These four signals are fused by a **logistic regression model trained on labeled pairs** (not hand-picked weights) into one calibrated confidence number. The ground truth for training comes from a real, defensible heuristic: **the same username appearing on two different marketplaces** — and critically, at evaluation time the username itself is stripped out of the text before scoring, so the system can't just cheat by string-matching the handle back out of the post body or a PGP key's UID field.

### 2.2 How Layer 2 (attribution) actually works

This is the differentiator. Once Layer 1 says "these aliases are probably one actor," Layer 2 asks: **did that actor ever slip up and leak something connecting their dark-web presence to the real world?**

The chain: **hidden service leaks a clearnet reference -> that clearnet domain -> Certificate Transparency log pivot -> the operator's other real-world infrastructure.**

Concretely: a misconfigured onion service might load an image, a favicon, or an analytics script from the operator's real (clearnet) domain by accident. Once you have that domain, Certificate Transparency logs (a public, auditable record of every TLS certificate ever issued) let you find every *other* domain sharing that same certificate or public key — which is very often the operator's other real infrastructure.

### 2.3 How Layer 3 (evidence/investigation) actually works

Every score the system produces comes with a **deterministic, non-fabricated evidence trail**: which post, which archive file, which scrape date, which content hash — all the way down. A natural-language investigator console (backed by a local LLM) lets an analyst ask questions like "what else does this operator run?" — but the LLM **never computes a score or decides a match**; it only retrieves and phrases results the deterministic pipeline already produced, and every sentence it generates has the underlying evidence rows shown right beneath it.

---

## 3. Real-world use case — a day in the life of an investigator

1. **Analyst opens the case console** (Streamlit UI) and picks an active investigation case.
2. **Search** for a wallet address, PGP fingerprint, onion address, or handle they've encountered — the system shows every alias/post that touched it, with source lineage (which archive, which date, which exact page).
3. **Clusters view** — the analyst sees pre-computed actor clusters: groups of aliases the system believes are one actor, ranked by confidence, annotated with which markets they span and the date range of activity.
4. **Pair inspector** — drill into any specific pair: see the four-channel score breakdown (style, topic, hard evidence, timing) and the literal shared evidence (the actual PGP key, the actual wallet) with surrounding post context.
5. **Evidence Trail** — a deterministic, ordered chain (alias -> post -> evidence -> alias -> post -> evidence -> fused score -> OpSec leak) that an investigator can read top to bottom as a chain of custody, not a black box.
6. **OpSec tab** — if the cluster includes a suspected operator's own infrastructure, run the misconfiguration scanner against it and pivot through Certificate Transparency to find sibling domains.
7. **Investigator console** — ask in plain English: *"This vendor leaked a clearnet domain -- what else does that operator run?"* and watch it chain a search + a CT pivot, with every claim backed by a visible evidence row underneath.
8. **Export** — CSV, JSON, or a full PDF report (methodology, per-cluster evidence, ethics statement, eval metrics) to hand off for further investigation.

This whole workflow works **even if Neo4j and the local LLM are both off** — the core pipeline, SQLite store, and Streamlit UI never depend on either being available. That's a deliberate reliability decision, not an oversight: a demo (or a real investigator's laptop) that dies because a graph database didn't start is not acceptable for a forensics tool.

---

## 4. Architecture (technical)

```
dnmarchives (archive.org, public historical corpus)
        |  tar.xz -> stream-parse (never extracted to disk) -> dedupe -> SQLite
        v
    ingest/            posts(market, alias, ts, body, lineage)
        |
   +----+--------------+---------------+
   v    v               v               v
stylometry/       evidence/       temporal/
char n-gram +     PGP . BTC .     hour histogram +
MiniLM embed      onion . email   TZ estimate
   |    |               |               |
   +----+-------+-------+---------------+
                v
           fusion/         5-6 features -> LogisticRegression -> calibrated P(same actor)
                |
      +---------+----------------------+
      v                                v
   graph/  networkx components,     opsec/   leak scan + CT pivot
           centrality -> clusters             (Layer 2 -- capability #1)
      |        |
      |        +--> Neo4j projection (optional; ad-hoc Cypher, browser viz)
      v
   explain/   evidence -> plain-language reason (template-first, optional LLM polish)
      v
   ui/ + export/   Streamlit console . CSV/JSON/PDF
      v
   agent/   LangChain investigator -- READ-ONLY, natural-language query over results
```

**Core invariant:** every pipeline stage (`ingest`, `evidence`, `stylometry`, `fusion`, `graph`, `opsec`, `explain`) is a plain, standalone-callable Python function *before* it's ever wired into LangGraph orchestration. Delete the LangGraph wrapper and every stage still runs from the CLI — the framework is a wrapper around the pipeline, never the owner of its logic. This is enforced by an actual test (`test_no_framework_leak.py`) that walks every source file's imports and asserts `langchain`/`langgraph` only appear inside the orchestration/agent layers.

### 4.1 Module-by-module

| Module | What it does | Key technical detail |
|---|---|---|
| `ingest/` | Streams tar.xz archives member-by-member (never extracts to disk), parses SMF/phpBB forum HTML, dedupes by `(market, msg_id)` keeping the newest scrape | `INSERT OR REPLACE` in ascending scrape-date order -- `OR IGNORE` would silently keep the *oldest* copy |
| `evidence/` | Extracts PGP fingerprints, crypto addresses, onion/clearnet domains, emails from post bodies | Two-stage filter: regex candidate -> checksum validation (base58check for BTC, bech32, PGP parse) -- a regex match alone is not evidence |
| `stylometry/` | Char n-gram TF-IDF (style, topic-robust) + MiniLM sentence embeddings (topic/semantic), scored on separate channels | FAISS blocking (top-50 neighbours) + forced inclusion of any pair sharing hard evidence, so scoring stays sub-quadratic on tens of thousands of aliases |
| `temporal/` | Hour-of-day / day-of-week posting histograms, Jensen-Shannon similarity, circular-mean timezone estimate | Reported as a weak hypothesis with stated confidence, never a location claim |
| `fusion/` | Fits a `LogisticRegression` on the four channels + hard-evidence count, outputs a calibrated probability | Confidence is *learned*, not hand-tuned -- a `--heuristic` fixed-weight mode exists only as a documented fallback |
| `graph/` | `networkx` connected components = candidate actor clusters; degree/betweenness centrality surfaces the "core" alias bridging markets | Optional Neo4j projection of the *finished* graph -- nothing in the scoring path depends on a server being up |
| `opsec/` | Misconfiguration detectors (clearnet resource refs, `/server-status`, `.git/config`, `.env`, directory listings, default pages, TLS SAN) + Certificate Transparency pivot | Runs against the team's own deliberately-misconfigured demo Tor hidden service *and* against the historical corpus's own leaked references -- never against a real third-party service |
| `explain/` | Template-first plain-language explanations of every score; optional local-LLM (Ollama) polish that only rewrites the already-computed facts | If Ollama is unreachable, silently falls back to the template -- never blocks |
| `pipeline/` | LangGraph `StateGraph` wrapping the stages: checkpoint/resume, a genuine parallel branch (OpSec doesn't depend on fusion), auto-generated architecture diagram | Thin nodes only -- zero business logic lives inside a LangGraph node |
| `agent/` | LangChain tool-calling investigator console, 9 read-only tools (search evidence, get cluster, score pair, alias timeline, CT pivot, OpSec scan, Cypher query, get case) | SQLite opened `mode=ro`; Cypher tool rejects `CREATE`/`MERGE`/`DELETE`/`SET`/`DROP` by regex **and** connects with a read-only DB user -- the regex is a courtesy, the account is the actual control |
| `ui/` | Single-file Streamlit app, 6 views: Search, Clusters, Pair inspector, Evidence Trail, OpSec, Investigator | Every view degrades gracefully with Neo4j and/or the LLM off |
| `export/` | CSV (`clusters.csv`), JSON (full nested report), PDF (ReportLab -- cover, methodology, per-cluster page, ethics statement, eval appendix) | |

---

## 5. Real numbers this system actually produced

Everything below is from the real, ingested corpus (**912,511 posts, 49,357 aliases, 5 markets: cannabisroad3, nucleus, silkroad1, silkroad2, thehub** -- 2011-2015 historical archives, publicly hosted on archive.org), not synthetic or placeholder data.

**Evidence extracted** (128,333 rows total): clearnet references 66,499 . onion addresses 45,381 . PGP fingerprints 10,043 . emails 3,764 . BTC addresses 2,646.

**Fusion model** (`LogisticRegression`, learned, alias-disjoint train/test split so no alias leaks across the split):
```
coefficients: s_time 2.03, s_hard 1.68, s_embed 1.12, time_missing 1.05,
              s_char 0.34, log1p_n_shared_hard -0.32, intercept -2.16
```
Held-out PR-AUC: **0.768** (a fixed-weight heuristic baseline scores worse, 0.710 -- confirming the learned model earns its place, not just "AI for AI's sake").

**Three real cases, differing only by confidence threshold** (built to show the system is threshold-tunable, not a single hand-picked cutoff, and to give the demo more than one dataset to show):

| Case | Threshold | Precision (held-out) | Recall (held-out) | Clusters | Note |
|---|---|---|---|---|---|
| CASE-2026-001 | 0.83 (shipped default) | 1.00 | 0.0149 | 90 | Zero false positives -- conservative, defensible headline number |
| CASE-2026-002 | 0.70 | 1.00 | 0.0487 | 72 | Still zero false positives, ~5x recall -- empirically justified knee point |
| CASE-2026-003 | 0.65 | 0.81 | 0.109 | *(build in progress -- see live case table)* | Precision starts trading off meaningfully below here |

The threshold choice isn't arbitrary -- a precision/recall curve was computed directly against the real labeled pairs before picking 0.70 and 0.65, and precision stays at a perfect 1.0 all the way down to 0.70 before it starts dropping.

**OpSec / Layer 2, live-verified**: scanned the team's own deliberately misconfigured Tor hidden service, detected a planted clearnet image reference (`erowid.org`), pivoted through live Certificate Transparency logs, found a real sibling domain (`archive.erowid.org`) sharing the same certificate. The same scanner also found a real leak inside the historical corpus itself -- a post explicitly tagged `***clearnet***` linking out to `dangerousminds.net`.

**Cross-market correlation, spot-verified for correctness (not just claimed)**: e.g. alias `Nightcrawler` on silkroad2 and `Nightcrawler` on thehub, confidence 0.870, sharing 6 hard-evidence items (a PGP fingerprint, an onion address, and 4 clearnet domains) -- independently re-verified by querying the raw evidence table for both aliases and confirming the intersection exactly matches the stored count. No fabrication found.

---

## 6. Legal / ethical scope (state this early in any presentation)

1. **No live Tor scraping, ever.** No interaction with any real marketplace or third-party hidden service, at any point.
2. **The only hidden service this system scans is one the team created**, on localhost, deliberately misconfigured for the demo.
3. **The corpus is historical and public** -- dnmarchives on archive.org, markets defunct since 2013-2015, the standard corpus in peer-reviewed cybercrime research.
4. **Certificate Transparency data is public by design** -- it exists so anyone can audit issued certificates.
5. **Wallets, PGP fingerprints, and handles are reported as pseudonymous identifiers with a confidence score -- never as an identity claim, never as a verdict.** This framing is enforced in the investigator agent's system prompt (forbidden phrasing: "same person," "same operator," "identity," "guilty") and in every UI/export surface.

---

## 7. What's been independently verified (not just claimed)

This session ran a live end-to-end verification pass -- real browser automation against the running app, real SQL queries against the real database -- and found (then fixed) real bugs rather than taking the code's word for it:

- **All 61 unit/integration tests pass**, including the ones that make the project's own safety claims checkable: `test_no_framework_leak.py` (orchestration never owns logic), `test_cypher_readonly.py` / `test_agent_readonly.py` (the agent truly cannot write), `test_redaction.py` (blind-eval protocol actually strips the handle, not just the label).
- **All 6 UI views work end-to-end against the real 912K-post corpus** (Playwright-driven), after fixing two real crashes found in the process:
  - `investigator.py` imported the local-LLM client unconditionally, so the whole app crashed if the package wasn't installed -- even though the Ollama-down *path* was designed to degrade gracefully, the import itself wasn't guarded.
  - `app.py` called a Streamlit widget parameter (`segmented_control(required=True)`) that doesn't exist in the installed Streamlit version -- a "coded against a remembered API instead of the installed one" class of bug.
- **A third bug found (and fixed) via graph rendering**: `pyvis`'s own HTML writer opens files with no explicit encoding, which defaults to Windows' cp1252 and crashes on any non-Latin-1 character -- fixed by generating the HTML directly and writing it as UTF-8.
- **A fourth, scalability-class bug found while building the extra cases**: `write_report_json()` has no cap on how many clusters it processes and does several DB round-trips *per cluster* -- fine at case 001's 375 clusters, a multi-hour hang at case 002's 6,632-node graph. Worked around by capping it the same way the PDF export already caps itself, without touching the underlying function.

The recurring pattern across three of these four bugs: **code was written against a remembered/assumed API or environment shape rather than the one actually installed** -- the exact failure mode the project's own build notes warn about for LangChain specifically, but which turned out to generalize to pyvis, Streamlit, and the export layer too.

---

## 8. Known limitations (say these before a judge asks)

- **Recall at the shipped 0.83 threshold is low (1.49%)** by design -- the system is tuned for zero false positives, not maximum coverage. The three-case threshold ladder exists specifically to make this tunability visible rather than hidden.
- **Forum-wide "shared" evidence isn't automatically a private link** -- some onion addresses and wallet lists appear on hundreds of aliases (the forum's own address, a widely-reposted scam-wallet blocklist) and shouldn't be pitched as a private key shared between two people. The system surfaces the raw count; a human still has to read it with judgment.
- **The ground-truth label (same username across markets) is a heuristic, not proof of identity** -- handle-squatting and impersonation are real and documented; this is stated explicitly rather than hidden, because a sharp judge will ask.
- **Neo4j Community Edition can't fully enforce a read-only database role** (`GRANT ROLE reader` isn't supported outside Enterprise) -- the actual control is the regex write-rejection plus never handing the UI/agent the writer credentials, and this limitation is documented rather than silently assumed away.
- **Case 003's full pipeline run (graph/opsec/explain/export) was still in progress as of this document's last update** -- see the live case table above for current status.

---

*This document is a study/reference artifact, not a slide deck. For the actual demo script and time-boxed pitch structure, see `SPEC.md` section 19.*