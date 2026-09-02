# CLAUDE.md — SUTRANETRA

This file is the standing operating contract for any agent (Claude Code or otherwise) working in this repository. It does not change per prompt. Read it once per session before touching code, and re-read it if a session gets long enough that context has been compacted.

The full technical specification lives in `SPEC.md` at the repo root. This file is not a summary of `SPEC.md` — it is the set of rules that govern *how* you work, independent of *what* you're building this week. Every numbered section below is a constraint an implementation must satisfy, not a suggestion.

Keep this file aligned with `AGENTS.md`.

## 1. What this system is

**SUTRANETRA** (*Sutra* = thread/connection, *Netra* = eye/vision) — *"The eye that follows the hidden threads."*

It attributes pseudonymous dark-web marketplace actors to real-world infrastructure, for SIH26151 (NTRO). It has **three layers** that must all work:

1. **Correlation** — which aliases are probably the same actor (stylometry + hard evidence + graph).
2. **Attribution** — which of those actors leak infrastructure that can lead investigators outward (OpSec scanning + CT-log pivoting).
3. **Evidence / Investigation** — why an investigator should believe the result, what exactly was observed, and what they should investigate next (`explain/` reason + **Evidence Trail**, UI/exports, read-only investigator agent, Neo4j Cypher, `cases`).

A submission that only does correlation is not this project — it's the generic version this spec was written to beat. Attribution without the third layer leaves a score without a case file. If you are ever unsure which layer a piece of work serves, ask before writing it. Keep this framing aligned with `AGENTS.md` and `SPEC.md` §1.

Use **SUTRANETRA** on all judge-facing surfaces (UI title, PDF cover, slide decks, exports). Do not ship under the old working title.

## 2. Non-negotiable architectural invariants

These decisions were made deliberately in `SPEC.md` §0 after an earlier draft got them wrong. Do not re-litigate them mid-build.

1. **The deterministic pipeline is the core; frameworks are wrappers.** Every pipeline stage (`ingest`, `evidence`, `stylometry`, `fusion`, `graph`, `opsec`, `explain`) is a plain, standalone-callable Python function/module before it is ever wired into LangGraph. LangGraph nodes call these functions; they never contain scoring, extraction, or business logic themselves. If you could delete `src/pipeline/graph.py` and the system still produces correct output via the CLI, the invariant holds. If you can't, it's broken — fix it before adding anything else.
2. **The investigator agent is read-only, always.** No LangChain tool writes to SQLite or Neo4j. This is enforced by connection mode (`file:...?mode=ro`, a read-only Neo4j role/user), not by convention or prompt wording. The agent retrieves and phrases; it never computes a verdict, never decides a match, never touches `pair_scores` except to read it.
3. **Confidence is learned, never hand-tuned in the shipped path.** `fusion/model.py` fits a `LogisticRegression` on labeled pairs. The `--heuristic` fixed-weight mode exists only as a fallback if the labeled set turns out too small — it is not the default, and if you use it, say so explicitly in every place confidence is reported.
4. **Neo4j and Ollama are optional at runtime; SQLite + networkx + templates are not.** Every export, every cluster view, every explanation must work with `--no-neo4j` and with Ollama unreachable. Test both degraded paths before considering a step done, not after.
5. **Two config profiles exist: `dev` and `demo`.** `dev` has the Neo4j sink and LLM polish off — you should not need a running server to iterate. `demo` has both on. Never hand-wave which profile a test or a demo run used.
6. **Evaluation is blind.** At scoring time, the alias/username string is stripped from both sides of a pair before it reaches the stylometry vectorizers — not just from the reported label. If a feature computation ever has access to the alias string it's currently scoring, that's a data leak, and the PR-AUC number that results from it is not a claim you can defend on stage.
7. **Report the honest number even when it's worse.** Blocking recall gets reported both with forced-inclusion of evidence/eval pairs (the number that will appear in the demo) and without it (the number that answers "would this work in production"). Never report only the flattering one.

## 3. Repo map

```
sutranetra/                 # product name: SUTRANETRA
├── SPEC.md              # the full technical spec — the source of truth for every field, selector, formula, and schema
├── AGENTS.md             # agent operating contract (keep in sync)
├── CLAUDE.md             # this file
├── config.yaml            # dev/demo profiles, thresholds, market list
├── data/                  # gitignored — raw archives, sqlite db, CT cache
├── src/                   # ingest/ evidence/ stylometry/ temporal/ fusion/ graph/ opsec/ explain/ pipeline/ agent/ export/ ui/
├── tests/
└── docs/
    ├── architecture.png    # generated, not hand-drawn (SPEC.md §16.1)
    ├── ethics.md
    └── build-log.md
```

Full field-level detail (schemas, selectors, API shapes, formulas) lives in `SPEC.md`. Do not duplicate it here and do not let it drift — if an implementation detail changes during the build, update `SPEC.md`, not just the code.

## 4. How to execute a prompt

Prompts live in `prompts/NN-name.md`, numbered in build order. For each one:

1. Read the prompt in full before writing anything. Read the `SPEC.md` sections it references.
2. Confirm the prompt's **Preconditions** are actually met — run the check, don't assume the previous step finished cleanly.
3. Implement only what the prompt asks for. A prompt that says "implement the PGP extractor" is not an invitation to also start the BTC extractor because it's adjacent — that's the next prompt, and pipelining ahead makes the Definition of Done for *this* prompt meaningless to check.
4. Run every item in the prompt's **Definition of Done** yourself. Do not report a step complete on the basis that the code "should" work — run it, look at the actual output, and quote the actual numbers/rows/assertions back in your summary.
5. Run every test the prompt lists. All must pass. A skipped test is a failed step.
6. If anything fails, stop and report exactly what failed and why — do not patch around it by weakening the check, and do not silently move to the next prompt with a known-broken step behind you.
7. End your turn with a short status block: which Definition-of-Done items passed, which tests passed, and — if relevant — the actual metric produced (row counts, PR-AUC, number of findings, etc.), not just "done."

Never batch multiple prompt files into one implementation pass. Each one is a checkpoint for a reason — the human running this needs to know, after every single prompt, whether the build is still on track.

## 5. Correctness rules that protect the pitch

These are the specific technical rules that, if silently violated, make a demo-day claim false. They are called out here because they are easy to get subtly wrong and hard to notice once wrong — a broken version still runs and still produces a number, just the wrong one.

- **Never extract the archives to disk.** Stream every tar member (`tarfile.extractfile(...).read()`). The disk budget in `SPEC.md` §20 assumes this; violating it can fill a demo laptop's disk mid-ingest.
- **Dedupe by `(market, msg_id)`, newest scrape date wins, via `INSERT OR REPLACE` processed in ascending scrape-date order.** `INSERT OR IGNORE` silently keeps the *oldest* copy — this is the opposite of correct and will not throw an error, it will just quietly corrupt the corpus.
- **Crypto-address extraction is a two-stage filter: regex candidate, then checksum validation.** A regex match alone is not evidence — ship the unit test with real positives and the known MD5-hash false positive from the sample corpus, and do not consider the extractor done until that test exists and passes.
- **Alias redaction at eval time is not optional and is not satisfied by removing the label column.** If the handle string (or an underscore/hyphen/digit-suffix/leetspeak variant of it) still appears inside the post body or a PGP UID that gets vectorized, the system is measuring string matching, not stylometry. This must have its own test, not just be assumed from the redaction function existing.
- **Confidence formulas saturate as specified** (`S_hard = 1 - 0.5^k_weighted`) — do not linearize them "for simplicity." The saturation is what makes one strong hard-evidence match dominate several weak ones, which is the intended behavior.
- **Every third-party network call (CT logs, archive.org) is cache-first.** The demo replays from `data/cache/`; live queries are opt-in via an explicit flag. A live external API is never allowed to be a single point of failure for a stage demo.
- **The `test_no_framework_leak.py` test is not decorative.** It is the only thing that makes the "wrapper, not owner" claim in §1 checkable rather than aspirational. Do not let it be the last test written for a section — write it as soon as the section it's checking exists.
- **Every post carries immutable source lineage** (`source_archive`, `scrape_date`, `source_member_path`, `content_sha256`). Dedupe must update lineage with the winning scrape. A system that cannot answer "where did this evidence come from?" down to the archive member is incomplete.
- **Scored results are case-scoped.** `pair_scores`, `clusters`, and `opsec_findings` always carry `case_id`. Never overwrite another case's rows. Case metadata (`corpus_snapshot`, `config_hash`, `model_version`, `threshold`) is what makes a run repeatable under judge questioning.
- **Evidence Trail is deterministic and non-inventive.** `explain/trail.py` builds the ordered chain the UI shows; it never fabricates OpSec/CT steps. Do not reimplement trail logic inside Streamlit.

## 6. Environment discipline

Install the core scientific/ingest stack first and confirm the pipeline runs end-to-end from the CLI with **no agentic or graph-database packages installed at all**. Only then install the LangGraph/LangChain pin group, confirm the wrapper still delegates correctly, and only after that install `neo4j`/`langchain-neo4j` as a separate, skippable layer. If a dependency resolver conflict shows up, it must never be able to take down the core ingest/scoring path — that's the entire reason for the staged install order.

Before writing any LangChain/LangGraph agent code, inspect the actually-installed package (`dir()` on the relevant module) rather than trusting training data or an online tutorial — both frameworks move fast enough that a remembered API shape is a good way to burn half a day. `SPEC.md` §16 flags this explicitly; treat it as binding.

## 7. Legal and ethical operating constraints — hard rules, not framing copy

1. No live Tor scraping, no interaction with any real marketplace or third-party hidden service, ever, at any point in this build, including "just to check."
2. The only hidden service this system scans is one created by this team, on localhost, deliberately misconfigured for the purpose of the demo.
3. Wallets, PGP fingerprints, and handles extracted from the historical corpus are stored and reported as pseudonymous identifiers with a confidence score — never as an identity claim, never as a verdict. Every UI surface and every export must reflect that framing in its wording.
4. `docs/ethics.md` is a required deliverable, not an afterthought — write it alongside the corpus/legal-scope work, not at the end.

## 8. What NOT to build

Auth, multi-tenancy, CI/CD, Docker, monitoring/alerting, autoscaling, a REST API, real-time streaming ingestion, a custom frontend framework, a message queue. None of it is judged, none of it demonstrates whether attribution works, and every hour spent on it is an hour not spent on the OpSec/CT-pivot capability, which is the part that actually differentiates this submission. If a prompt or a tangent starts drifting toward any of this list, stop and say so instead of building it.

## 9. Priority under time pressure

If the deadline is closing in and something has to be cut, the cut order is fixed and is not a judgment call to make under pressure:

1. Never cut the OpSec leak scanner + CT pivot (`SPEC.md` §12). It is the one artifact that is a real-world result rather than a correlation. Losing it turns this into a generic alias-clustering project.
2. Never cut the blind-evaluation protocol or the edge-case tests (`SPEC.md` §11). A number with no rigor behind it is worse than a smaller number with rigor behind it, in front of a technical judge.
3. Never cut the Evidence Trail tab (`SPEC.md` §15) or post source lineage (`SPEC.md` §6.1) — together they answer "how did you reach this?" and "where did it come from?"
4. Drop the natural-language investigator agent before dropping the Neo4j Cypher console it sits on top of — the console alone still answers "query capabilities."
5. Drop the LLM explanation polish before dropping the template explanations — templates are correct, deterministic, and sufficient; the LLM only rewrites their prose.
6. Drop a live pipeline run in favor of pre-computed cached results before dropping any of the above.

## 10. Status discipline

Never say a prompt is "complete" or "working" without having just run the thing that proves it. If you have not executed the Definition of Done for the current prompt in this session, you do not yet know whether it's done, and you should say that instead of guessing.
