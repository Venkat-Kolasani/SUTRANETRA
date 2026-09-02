# SUTRANETRA — SIH26151 Dark Web Threat Actor De-anonymization

**Project name:** SUTRANETRA  
**Etymology (Sanskrit-rooted):** *Sutra* = thread / connection · *Netra* = eye / vision  
**Tagline:** *"The eye that follows the hidden threads."*

**Org:** NTRO · **Theme:** Blockchain & Cybersecurity · **Type:** Software · **Deadline:** 20 Sep 2026 · **Cap:** 500 ideas

> This document is the complete build spec for **SUTRANETRA**. It is written to be handed to an implementing agent as the sole context for the build. Every path, selector, URL and field name below was verified against the real data on 27 Aug 2026, not assumed. Use the product name **SUTRANETRA** on slides, UI chrome, reports, and judge-facing copy — not the old working title.

---

## 0. What changed from the first draft (read this first)

| Old plan | Problem | Now |
|---|---|---|
| Skipped Tor infrastructure analysis for "legal safety" | This is PS capability #1 and the only part that produces a **real-world** artifact. Dropping it means we build alias correlation and call it de-anonymization. | Built, using **our own** deliberately-misconfigured hidden service + **public** Certificate Transparency logs. Zero exposure. |
| CrimeBB corpus | Needs a custom data-sharing agreement signed by our institution. Weeks of lead time. Won't land before 20 Sep. | **Darknet Market Archives (dnmarchives)** on archive.org. Ungated direct download, verified working, 48 forum archives across ~20 markets. |
| VeriDark as drop-in replacement | Correction: only *MiniDarkReddit* (204/412/412 pairs) is a direct link. Agora / SilkRoad1 / DarkReddit+ are **Zenodo restricted-access** — request form + approval. Not instant. | dnmarchives is primary. File the Zenodo request in parallel; if granted, use it only to compare against published baselines. Not on the critical path. |
| Threshold-tuned against synthetic planted pairs | Self-grading. A judge will say so. | Real ground truth: same username across two different marketplaces. Username stripped at eval time. Reportable precision/recall. |
| `all-MiniLM-L6-v2` alone | Semantic model. Mean-pooled per alias it clusters by **topic**, not style — two unrelated cannabis vendors score high because both discuss cannabis. Manufactures the exact false positives §11 claims to catch. | Two-channel: char n-gram TF-IDF (style) **+** embeddings (semantic), scored separately, fused. |
| Hand-set fusion weights `w1, w2` | Indefensible under questioning ("why 0.7?"). | Logistic regression over 5 features, fit on labeled pairs. Calibrated probability out, and the learned coefficients *are* the answer to "why". |
| LangGraph orchestration owning the pipeline | If the framework owns business logic, a framework failure is a total failure, and scoring stops being reproducible. | **Kept, repositioned.** Deterministic functions stay the core and still run standalone. LangGraph wraps them as thin nodes (checkpoint/resume, parallel opsec branch, generated diagram) and LangChain adds a read-only **investigator agent** for natural-language query. Full design in §16. |
| Neo4j owning the graph | If clustering depends on a running server, the demo dies when the server doesn't start. | **Kept, repositioned (§13.1).** `networkx` computes components and centrality in-process — that path never needs Neo4j. Neo4j is a **projection** of the finished graph, added for ad-hoc Cypher in front of an investigator, Neo4j Browser visualisation, and multi-user query. Optional at runtime, valuable in the pitch. |
| Working title `darkattrib` | Fine for a repo nickname; weak as a judge-facing brand. | Product name **SUTRANETRA** — Indian-rooted (*sutra* = thread/connection, *netra* = eye/vision); tagline *"The eye that follows the hidden threads."* Package/repo directory in this kit may still say `darkattrib-buildkit`; the shipped system and all UI/report titles use **SUTRANETRA**. |
| No exports, no query UI | PS explicitly demands CSV/JSON/report + query via GUI. Free marks left on the table. | §15. |
| Pitch framed as two halves (correlation + attribution) | A calibrated score without provenance, explanation, and next-step query is incomplete for a forensics evaluator. | Formalized **three layers** in §1: Correlation → Attribution → Evidence / Investigation (`explain/` + UI/export + agent + Cypher). |
| Posts identified only by `(market, msg_id)` | A judge asking "where exactly did this evidence come from?" could not walk past the post row to the archive member. | Every post carries immutable source lineage (§6.1): `source_archive`, `scrape_date`, `source_member_path`, `content_sha256`. |
| Results organized only as aliases / pairs / clusters | Looked like a data-science script, not an investigation platform; hard to reproduce a specific run. | Explicit `cases` table (§6.2) scopes scored pairs, clusters, opsec findings, and reports under a case id with corpus snapshot, config hash, model version, and threshold. |
| UI showed tables and scores but not the decision path | A judge asking "how did you reach this conclusion?" had to reverse-engineer joins mentally. | **Evidence Trail** tab (§15): a vertical, ordered chain from alias → post → hard evidence → peer alias → confidence → clearnet/CT pivot. |

---

## 1. What the PS actually asks vs what we build

NTRO wording: *"deanonymize dark web threat actors by continuously gathering their footprints from a range of sources"* and connect them to **real-world identities**.

| PS capability | Our module | Status |
|---|---|---|
| **1.** Detect misconfigurations in Tor hidden services — exposed pages, SSL certs linked to clearnet domains | `opsec/` — leak scanner + CT-log pivot | Build. **This is the differentiator.** |
| **2.** Actor mapping across marketplaces — handles, crypto keys, wallets, trust relationships | `evidence/` + `graph/` | Build |
| **3.** AI attribution of rebranded/migrated personas — writing style + behaviour | `stylometry/` + `fusion/` | Build |
| Data collection, storage, contextualisation, query via GUI | `ingest/` + SQLite + `ui/` + `agent/` (natural-language, §16.2) + Neo4j/Cypher console (§13.1) | Build |
| Output CSV, JSON, report | `export/` | Build |

**The framing that wins the pitch — three layers, not two:**

```
CORRELATION          Which aliases are probably the same actor?
      ↓              (stylometry + hard evidence + graph — PS #2/#3)
ATTRIBUTION          Which of those actors leak infrastructure
      ↓              that can lead investigators outward? (opsec + CT — PS #1)
EVIDENCE /           Why should an investigator believe this result,
INVESTIGATION        what exactly was observed, and what should they
                     investigate next? (explain + UI/export + agent + Cypher)
```

Capability #2 and #3 produce *correlation between pseudonyms*. Capability #1 produces a *real-world artifact* — a clearnet domain, an IP, a hosting provider. Most teams will build #2/#3 only, because "dark web infrastructure" sounds legally radioactive. It isn't, when the infrastructure is your own.

Stopping at attribution still leaves a score without a case file. The third layer — `explain/`, Streamlit pair/cluster views, CSV/JSON/PDF exports, the read-only investigator agent, and Neo4j Cypher — is what turns a confidence number into something an NTRO analyst can interrogate: provenance rows, feature breakdowns, shared evidence, and a concrete next step. Say the full stack on stage: **correlate → attribute → evidence the claim**.

Modules by layer:

| Layer | Answers | Modules |
|---|---|---|
| **Correlation** | Same actor? | `stylometry/`, `evidence/` (hard links), `temporal/`, `fusion/`, `graph/` |
| **Attribution** | Outward infrastructure leak? | `opsec/` (leak scan + CT pivot) |
| **Evidence / Investigation** | Why believe it, what was observed, what next? | `explain/` (reason + **Evidence Trail**), `ui/`, `export/`, `agent/`, Neo4j projection (§13.1), `cases` (§6.2) |

---

## 2. Legal and ethical scope — state this on slide 2

1. **We never touch live criminal infrastructure.** No Tor scraping, no marketplace access, no interaction with any third-party hidden service.
2. **Corpus is historical and public.** The Darknet Market Archives are publicly hosted on archive.org, cover markets defunct since 2013–2015, and are the standard corpus in peer-reviewed cybercrime research.
3. **The hidden service we scan is one we create ourselves**, on localhost, deliberately misconfigured to demonstrate detection.
4. **CT log data is public by design.** Certificate Transparency exists so anyone can audit issued certificates.
5. **Intended use is law-enforcement attribution** for a government agency (NTRO), which is the use case this class of research explicitly supports.
6. Wallets and PGP fingerprints found in the corpus are treated as **pseudonymous identifiers**, not identities. The system reports *evidence and confidence*, never a verdict.

Include an ethics statement in the final report. It costs nothing and it is a differentiator with a government evaluator.

---

## 3. Architecture

```
                        ┌──────────────────────────────────────┐
                        │  dnmarchives (archive.org, public)   │
                        │  20 markets · SMF/phpBB forum dumps  │
                        └──────────────────┬───────────────────┘
                                           │
                                   ┌───────▼────────┐
                                   │  ingest/       │  tar.xz → parse → dedupe → SQLite
                                   └───────┬────────┘
                                           │  posts(market, alias, ts, body, source lineage)
                    ┌──────────────────────┼──────────────────────┐
                    │                      │                      │
            ┌───────▼───────┐      ┌───────▼───────┐      ┌───────▼───────┐
            │ stylometry/   │      │ evidence/     │      │ temporal/     │
            │ char n-gram   │      │ PGP · BTC ·   │      │ hour-of-day   │
            │ + embeddings  │      │ onion · clear │      │ histogram +   │
            │               │      │ net domains   │      │ TZ estimate   │
            └───────┬───────┘      └───────┬───────┘      └───────┬───────┘
                    └──────────────────────┼──────────────────────┘
                                   ┌───────▼────────┐
                                   │  fusion/       │  5 features → LogisticRegression
                                   │                │  → calibrated P(same actor)
                                   └───────┬────────┘
                                           │
                    ┌──────────────────────┴──────────────────────┐
            ┌───────▼───────┐                              ┌──────▼──────┐
            │  graph/       │  networkx, components,       │  opsec/     │  ← capability #1
            │  centrality   │  cross-market edges          │  leak scan  │
            │      │        │                              │  + CT pivot │
            │      └────────┼──► Neo4j projection (§13.1)  └──────┬──────┘
            │               │    Cypher · Browser · optional      │
            └───────┬───────┘                                     │
                    └──────────────────┬──────────────────────────┘
                              ┌────────▼────────┐
                              │ explain/        │  evidence → plain-language reason
                              └────────┬────────┘
                              ┌────────▼────────┐
                              │ ui/  +  export/ │  query GUI · CSV · JSON · PDF report
                              └────────┬────────┘
                                       │
                              ┌────────▼──────────────────────────┐
                              │ agent/  — LangChain investigator  │  natural-language query
                              │ READ-ONLY tools over the results  │  (§16.2, never scores)
                              └───────────────────────────────────┘

   ── every stage above is a plain function, callable standalone from the CLI ──
   ── LangGraph (§16.1) wraps them as thin nodes: checkpoint/resume,          ──
   ──   parallel opsec branch, auto-generated architecture diagram            ──

   Layer map (see §1):
     CORRELATION ………… stylometry + evidence + temporal → fusion → graph
     ATTRIBUTION …………… opsec (leak scan + CT pivot)
     EVIDENCE / INV ……… explain → ui/export → agent (+ Neo4j Cypher)
                              ↑ cases (§6.2) scope every investigation run
                              ↑ post source lineage (§6.1) closes the forensic chain
```

One process, one SQLite file, no server, no message bus. The orchestration layer is a **wrapper**, never the owner: delete `pipeline/graph.py` and every stage still runs. Correlation and attribution without the evidence/investigation layer are incomplete for a forensics pitch: a calibrated probability that cannot be explained, exported, or queried is not usable by an investigator.

**Forensic chain (must be walkable in the UI and in `report.json`):**

```
case  →  cluster  →  pair  →  evidence  →  post  →  archive member
                                                      (source_archive /
                                                       scrape_date /
                                                       source_member_path /
                                                       content_sha256)
```

---

## 4. Repo layout

```
sutranetra/
├── README.md
├── requirements.txt
├── config.yaml               # paths, thresholds, market list
├── data/
│   ├── raw/                  # downloaded .tar.xz  (gitignored)
│   ├── db/attrib.sqlite      # canonical store    (gitignored)
│   └── cache/ct/             # cached CT responses — demo replays from here
├── src/
│   ├── ingest/
│   │   ├── fetch.py          # download archives from archive.org
│   │   ├── smf_parser.py     # SMF forum HTML → posts
│   │   ├── phpbb_parser.py   # fallback layout
│   │   └── load.py           # dedupe + write to SQLite
│   ├── evidence/
│   │   ├── pgp.py            # PGP block → fingerprint
│   │   ├── crypto_addr.py    # BTC base58check + bech32 validation
│   │   ├── onion.py          # .onion + clearnet domain extraction
│   │   └── extract.py        # runs all extractors over posts table
│   ├── stylometry/
│   │   ├── char_ngram.py     # TF-IDF char 3-5grams → cosine
│   │   └── embed.py          # sentence-transformers → cosine
│   ├── temporal/
│   │   └── activity.py       # hour histogram, JS divergence, TZ estimate
│   ├── fusion/
│   │   ├── features.py       # alias pair → 5-dim feature vector
│   │   ├── model.py          # LogisticRegression fit/predict/persist
│   │   └── evaluate.py       # precision/recall/PR-AUC on held-out labels
│   ├── graph/
│   │   ├── build.py          # edges → networkx → components + centrality
│   │   └── neo4j_sink.py     # project finished graph into Neo4j (§13.1, optional)
│   ├── opsec/
│   │   ├── scanner.py        # hidden-service misconfig detection
│   │   ├── ct_pivot.py       # cert → clearnet domain via CT logs
│   │   └── demo_target/      # our own deliberately-broken service
│   ├── explain/
│   │   ├── reason.py         # template-first, LLM optional
│   │   └── trail.py          # ordered Evidence Trail steps for a pair/cluster (§15)
│   ├── pipeline/
│   │   ├── case.py           # create/open/complete cases; config_hash (§6.2)
│   │   └── graph.py          # LangGraph StateGraph over the stages (§16.1)
│   ├── agent/
│   │   ├── tools.py          # read-only LangChain tools (§16.2)
│   │   └── investigator.py   # tool-calling agent, ChatOllama
│   ├── export/
│   │   └── writers.py        # CSV / JSON / PDF
│   └── ui/
│       └── app.py            # Streamlit
├── tests/
└── docs/
    ├── architecture.png
    └── ethics.md
```

---

## 5. Data acquisition — verified

**Source:** `https://archive.org/download/dnmarchives/<name>` — public, no auth, no signup. Verified 27 Aug 2026.

Recommended set (cross-market overlap is the whole point — pick markets whose lifetimes overlap):

| File | Size | Why |
|---|---|---|
| `silkroad1-forums.tar.xz` | 271 MB | 2011–2013, the canonical corpus |
| `agora-forums.tar.xz` | 869 MB | 2013–2015, large, overlaps SR2/Evolution |
| `silkroad2-forums.tar.xz` | 575 MB | Direct SR1 successor — **migration cases live here** |
| `evolution-forums.tar.xz` | 1178 MB | 2014–2015, exit-scammed, vendors migrated out |
| `thehub-forums.tar.xz` | 276 MB | Cross-market meta-forum — vendors from everywhere |
| `nucleus-forums.tar.xz` | 134 MB | Smaller, good for a fast dev loop |
| `cannabisroad3-forums.tar.xz` | 2.2 MB | **Start here.** Tiny, parses in seconds, already inspected |

Start with `cannabisroad3` → get the parser green → then `nucleus` → then the big four.

**Do not commit archives to git.**

### Verified archive structure

```
cannabisroad3-forums/
  2014-11-18/                        ← scrape date; SAME PAGES REAPPEAR PER DATE
    index.php?topic=440.0            ← thread page (SMF), this is what we parse
    index.php?topic=43.60            ← .60 = post offset within thread
    index.php?action=profile;u=389   ← profile page
    avatars/...  Themes/...          ← assets, skip
  2014-11-21/  2014-11-23/  2014-11-25/
```

- 10,914 members in that one 2.2 MB archive; only ~10,490 non-asset, and **4 scrape dates duplicate the same threads**. Dedupe is mandatory or every post is counted 4×.
- Filter to files whose name contains `index.php?topic=`.
- Dedupe key: `(market, msg_id)` where `msg_id` comes from the post's DOM id. Keep the newest scrape date. The winning row must also carry that scrape's source lineage fields (§6.1) — never keep an old `scrape_date` on a replaced body.
- **Never extract to disk.** Stream members with `tarfile.extractfile(member).read()`. Agora is 869 MB compressed and roughly 8–10 GB extracted; the disk budget in §20 assumes you stream.
- `load.py` uses `INSERT OR REPLACE`, processing scrape dates **ascending**, so the newest scrape wins. `INSERT OR IGNORE` would silently keep the oldest copy and lose later edits.

---

## 6. Ingestion — SMF parser (selectors verified against real HTML)

SMF 2.0 markup, confirmed by reading `cannabisroad3-forums/2014-11-25/index.php?topic=440.0`:

```python
# src/ingest/smf_parser.py
from bs4 import BeautifulSoup
from dataclasses import dataclass
from datetime import datetime, date
import re

@dataclass
class Post:
    market: str
    msg_id: int          # from id="msg_4111"
    alias: str           # display name
    user_id: int | None  # from action=profile;u=389
    thread_id: int
    subject: str
    ts: datetime | None  # UTC-naive, as scraped
    body: str            # plain text, HTML stripped
    raw_html: str        # keep — evidence extractors need PGP blocks intact
    onion_host: str | None  # forum's own .onion, from absolute URLs
    # Immutable source lineage (§6.1) — set by the loader from the tar member, not guessed later
    source_archive: str       # e.g. "cannabisroad3-forums.tar.xz"
    scrape_date: date         # from the scrape-date directory name, e.g. 2014-11-25
    source_member_path: str   # exact tar member path inside the archive
    content_sha256: str       # sha256 hex of UTF-8 raw_html (forensic content fingerprint)

def parse_topic_page(
    html: str,
    market: str,
    *,
    source_archive: str,
    scrape_date: date,
    source_member_path: str,
) -> list[Post]:
    ...
```

Verified selector map:

| Field | Selector / pattern | Verified sample |
|---|---|---|
| post block | `div.post_wrapper` | one per post |
| alias | `div.poster h4 a` text | `AngelEyes` |
| user_id | `href` → `action=profile;u=(\d+)` | `389` |
| membergroup | `li.membergroup` | `Cannabis Road Legacy Vendor` — **vendor flag, keep it** |
| post count | `li.postcount` | `Posts: 139` |
| karma | `li.karma` | `Karma: +45/-0` — **trust signal, PS asks for trust relationships** |
| subject | `div.keyinfo h5 a` | `Mango & Terpenes -- Making Highs Higher?` |
| timestamp | `div.keyinfo div.smalltext`, strip `« on: … »` | `July 10, 2014, 03:26:03 AM` |
| msg_id | `div.post div.inner` → `id="msg_4111"` | `4111` |
| body | `div.post div.inner` | HTML; `<br />` → `\n`, unescape entities |
| onion host | any absolute `http://([a-z2-7]{16}|[a-z2-7]{56})\.onion` | `forumz2gljo2vhzb.onion` |

Timestamp format: `%B %d, %Y, %I:%M:%S %p`. SMF also emits relative forms (`Today at 03:26:03 AM`) — resolve against the scrape date, and if it can't be parsed set `ts = None` rather than guessing. Posts with `ts = None` are excluded from the temporal feature only, not from the corpus.

**Encoding:** decode with `utf-8, errors='replace'`. These are 2014 scrapes; some are mojibake. Do not crash on them.

**phpBB fallback:** a few markets are phpBB, not SMF (`div.postbody`, `p.author`). Write `phpbb_parser.py` only when a market actually fails — detect by checking for `post_wrapper` and dispatching. Don't build it speculatively.

### 6.1 Immutable source lineage on every post

`(market, msg_id)` identifies a post logically. That is not enough for a forensics question. Every stored post also records **where the bytes came from**:

| Column | Example | Purpose |
|---|---|---|
| `source_archive` | `silkroad1-forums.tar.xz` | which downloadable archive |
| `scrape_date` | `2014-11-25` | which scrape folder inside that archive won the dedupe |
| `source_member_path` | `silkroad1-forums/2014-11-25/index.php?topic=440.0` | exact tar member |
| `content_sha256` | `a3f1…` | sha256 hex of UTF-8 `raw_html` for the post block |

Rules:
1. Lineage is written at ingest time and never recomputed from memory later. If a field is missing, the load failed — do not backfill with guesses.
2. `content_sha256 = sha256(raw_html.encode("utf-8")).hexdigest()`. Hash the preserved HTML block, not the stripped `body`, so PGP armor and markup that affect evidence extraction are in the fingerprint.
3. On `INSERT OR REPLACE`, the winning (newest-scrape) row replaces lineage and content together. After dedupe, a judge asking "which scrape am I looking at?" must get the newest scrape's path, not a stale one attached to newer text.
4. Evidence rows already point at `post_id`. The forensic walk is therefore: **cluster → pair → evidence → post → archive member**. Exports and the pair/cluster UI must surface these four fields whenever a post is shown as supporting evidence.

### 6.2 Cases — investigation runs, not just tables of pairs

The corpus (`posts`, `aliases`, `evidence`) is shared and append-mostly. Scoring, clustering, OpSec findings, and reports are **case-scoped**. Without this, the system looks like a one-shot script; with it, it looks like an investigation platform and every demo number is tied to a reproducible run.

Example case card a judge should be able to open:

```
CASE-2026-001
  Corpus:   SilkRoad1 + Agora + Evolution   (snapshot JSON)
  Model:    fusion-v1                       (+ model file hash)
  Threshold: 0.83
  Config:   <config_hash>
  Run:      2026-09-03
  Status:   complete
  Result:   Cluster #17 …
```

```
case
 ├── aliases (via scored pairs / clusters — corpus rows, not copied)
 ├── evidence (corpus rows referenced by post_id / alias_id)
 ├── scored pairs     (pair_scores.case_id)
 ├── clusters         (clusters.case_id)
 ├── opsec findings   (opsec_findings.case_id)
 └── reports         (cases.report_path + export writers keyed by case_id)
```

`src/pipeline/case.py` owns create / open / complete:
- `case_id` — stable string, e.g. `CASE-2026-001` (or `CASE-YYYYMMDD-HHMMSS` when auto-minted by CLI).
- `corpus_snapshot` — JSON text: `{"markets": [...], "n_posts": N, "n_aliases": M}` taken at case creation (what was in the DB when this investigation started).
- `config_hash` — sha256 of a **canonical JSON** of the config keys that affect scoring/graphing (active profile, market list, fusion threshold, stylometry/embedding settings, model path). Do **not** hash machine-local absolute paths that would make two identical scientific runs look different.
- `model_version` — human label plus optional short content hash of the persisted fusion model file (e.g. `fusion-v1@ab12cd`).
- `threshold` — the confidence threshold used to materialize graph edges for this case.
- `status` — `created` → `running` → `complete` | `failed`.

LangGraph's `CaseState.case_id` (§16.1) must be the same id as `cases.case_id` — the orchestration wrapper opens/updates the case row; it does not invent a parallel identifier.

### Schema

```sql
-- ── Corpus (shared; posts carry immutable source lineage) ──────────────
CREATE TABLE posts (
  id INTEGER PRIMARY KEY,
  market TEXT NOT NULL,
  msg_id INTEGER NOT NULL,
  alias TEXT NOT NULL,
  user_id INTEGER,
  thread_id INTEGER,
  subject TEXT,
  ts TEXT,                       -- ISO8601, nullable
  body TEXT NOT NULL,
  raw_html TEXT NOT NULL,         -- required for evidence extractors + content_sha256
  membergroup TEXT,
  postcount INTEGER,
  karma_pos INTEGER, karma_neg INTEGER,
  onion_host TEXT,
  source_archive TEXT NOT NULL,
  scrape_date TEXT NOT NULL,      -- ISO date YYYY-MM-DD
  source_member_path TEXT NOT NULL,
  content_sha256 TEXT NOT NULL,   -- sha256 hex of UTF-8 raw_html
  UNIQUE(market, msg_id)
);
CREATE INDEX idx_posts_alias ON posts(market, alias);
CREATE INDEX idx_posts_content_hash ON posts(content_sha256);
CREATE INDEX idx_posts_source ON posts(source_archive, scrape_date);

CREATE TABLE aliases (
  id INTEGER PRIMARY KEY,
  market TEXT NOT NULL,
  alias TEXT NOT NULL,
  n_posts INTEGER, first_seen TEXT, last_seen TEXT,
  is_vendor INTEGER DEFAULT 0,
  UNIQUE(market, alias)
);

CREATE TABLE evidence (
  id INTEGER PRIMARY KEY,
  alias_id INTEGER REFERENCES aliases(id),
  post_id  INTEGER REFERENCES posts(id),
  kind TEXT NOT NULL,            -- pgp_fpr | btc | xmr | onion | clearnet | email
  value TEXT NOT NULL,
  context TEXT                   -- ±120 chars around the hit, for the report
);
CREATE INDEX idx_evidence_value ON evidence(kind, value);

-- ── Investigation runs ─────────────────────────────────────────────────
CREATE TABLE cases (
  case_id TEXT PRIMARY KEY,              -- e.g. CASE-2026-001
  created_at TEXT NOT NULL,              -- ISO8601
  corpus_snapshot TEXT NOT NULL,         -- JSON: markets, n_posts, n_aliases
  config_hash TEXT NOT NULL,             -- sha256 of canonical scoring config
  model_version TEXT NOT NULL,           -- e.g. fusion-v1@ab12cd
  threshold REAL NOT NULL,               -- edge threshold for this run
  status TEXT NOT NULL,                  -- created | running | complete | failed
  report_path TEXT,                      -- optional path to exported report bundle
  error TEXT                             -- set when status = failed
);

CREATE TABLE pair_scores (
  case_id TEXT NOT NULL REFERENCES cases(case_id),
  a_alias_id INTEGER NOT NULL,
  b_alias_id INTEGER NOT NULL,
  s_char REAL, s_embed REAL, s_hard REAL, s_time REAL, n_shared_hard INTEGER,
  confidence REAL,
  label INTEGER,                 -- 1 same / 0 different / NULL unknown (eval only)
  PRIMARY KEY (case_id, a_alias_id, b_alias_id)
);

CREATE TABLE clusters (
  case_id TEXT NOT NULL REFERENCES cases(case_id),
  cluster_id INTEGER NOT NULL,
  alias_id INTEGER NOT NULL REFERENCES aliases(id),
  confidence REAL,               -- cluster-level or member edge confidence summary
  PRIMARY KEY (case_id, cluster_id, alias_id)
);

CREATE TABLE opsec_findings (
  id INTEGER PRIMARY KEY,
  case_id TEXT NOT NULL REFERENCES cases(case_id),
  target TEXT NOT NULL,           -- demo onion / localhost URL / corpus note
  finding_kind TEXT NOT NULL,    -- clearnet_ref | server_status | git_config | …
  value TEXT NOT NULL,           -- leaked hostname, domain, path, header, …
  detail TEXT,                   -- free-form context for the report
  created_at TEXT NOT NULL
);
CREATE INDEX idx_opsec_case ON opsec_findings(case_id);
```

**Corpus vs case — do not blur this.** Re-ingesting is rare; re-scoring under a new threshold or model is common. Create a new `cases` row for each investigation run. Never overwrite another case's `pair_scores` / `clusters` / `opsec_findings`.

SQLite is correct here: single file, zero setup, ships in the demo folder, survives a laptop reboot on stage.

---

## 7. Evidence extraction (deterministic, hard signals)

Verified present in the corpus: scanning 654 thread pages of the 2.2 MB `cannabisroad3` archive found **23 pages containing `-----BEGIN PGP`** and Bitcoin addresses in post bodies. Both signals are genuine, not hypothetical.

### 7.1 PGP — `evidence/pgp.py`
- Extract `-----BEGIN PGP PUBLIC KEY BLOCK-----` … `-----END…-----` from `raw_html` (unescape entities first).
- Parse with `pgpy`: `PGPKey.from_blob()` → `key.fingerprint`.
- Store the **fingerprint**, not the armored blob. Fingerprint reuse across two aliases is the single strongest link in this system.
- Also catch bare fingerprints in signatures: `\b[0-9A-F]{40}\b` and `(?:[0-9A-F]{4}\s+){9}[0-9A-F]{4}`.
- Also capture `-----BEGIN PGP SIGNED MESSAGE-----` — signed vendor announcements are common and carry a key id.
- **`pgpy` chokes on some 2014-era keys** (old algorithms, malformed armor). On parse failure, fall back to regexing the key id / fingerprint out of the armor header and comments. Never drop the post because the key wouldn't parse.

### 7.2 Crypto addresses — `evidence/crypto_addr.py`
**Regex alone is wrong.** A naive `[13][a-km-zA-HJ-NP-Z1-9]{25,34}` over the sample returned `16936e5adb8a36cbb21d38beeb6f8e11` (an MD5 hash) and `3y4kBQhzP5dPh1AiMhNWU7HKLB3` (too short). Both false positives.

Required: regex candidate → **base58check validate** (decode, verify 4-byte SHA256d checksum) → keep. Bech32 (`bc1…`) validate separately. Monero: `4[0-9AB][1-9A-HJ-NP-Za-km-z]{93}` + checksum.

```python
def is_valid_btc(addr: str) -> bool:
    """Base58Check: last 4 bytes must equal sha256(sha256(payload))[:4]."""
```
Ship a unit test with the four real addresses found in the sample as positives and the MD5 hash as a negative. That test *is* the proof of rigour for this module.

### 7.3 Onion + clearnet — `evidence/onion.py`
- v2 `[a-z2-7]{16}\.onion`, v3 `[a-z2-7]{56}\.onion`.
- Clearnet domains in post bodies. **This matters more than it looks:** the sample contained a post explicitly tagged `***clearnet***` linking to `dangerousminds.net`. Actors leak clearnet references constantly — those domains feed straight into the CT pivot in §12.
- Emails: standard pattern, plus obfuscated forms (`name [at] domain [dot] com`).

### 7.4 Shared-evidence score
```
S_hard(A,B) = 1 - 0.5^(k_weighted)
k_weighted = 3.0·(shared PGP fprs) + 2.0·(shared wallets) + 1.0·(shared onion/clearnet/email)
```
Saturating, so one shared PGP key already yields ~0.88 and additional weak matches can't dilute it. Store `n_shared_hard` alongside for the report.

---

## 8. Stylometry — two channels, not one

### 8.1 Char n-gram (style) — `stylometry/char_ngram.py`
```python
TfidfVectorizer(analyzer='char_wb', ngram_range=(3,5),
                min_df=3, max_features=200_000, sublinear_tf=True)
```
- Fit on the **whole corpus**, transform per alias document (all of an alias's posts concatenated).
- `S_char = cosine(vec_A, vec_B)`.
- Character n-grams capture punctuation habits, spacing, typos, casing — topic-robust. This is the stylometry workhorse and the reason the system doesn't just cluster by product category.

### 8.2 Embeddings (semantic) — `stylometry/embed.py`
- `sentence-transformers/all-MiniLM-L6-v2`, CPU, batch 64.
- Per post, then mean-pool per alias. `S_embed = cosine(...)`.
- Keep it explicitly as a **topic/domain** signal. Do not present it as style.

### 8.3 Blocking (don't score N²)
50k aliases → 1.25 B pairs. Don't.
- Build a FAISS `IndexFlatIP` over char-n-gram vectors (reduced to 256 dims with `TruncatedSVD`), take top-50 neighbours per alias.
- **Force-include** every pair that shares any hard evidence, regardless of neighbour rank — those are the pairs that matter most and stylometry might miss them.
- Candidate set = top-50 neighbours ∪ hard-evidence pairs ∪ eval pairs.

**Report blocking recall separately — this is a trap otherwise.** Forcing eval pairs into the candidate set guarantees every true positive is present before scoring, which hides blocking's own recall loss and makes §11's recall number answer the wrong question. So also compute: *fraction of labelled positives that survive top-50 neighbours **without** forced inclusion*. That is the honest production number. Volunteering it is the same credibility move as §11.3.

### 8.4 Text hygiene (do this or the scores are garbage)
Before vectorising, strip from the body: quoted text (`div.quote`), signature blocks, PGP armor, URLs, and market boilerplate. Quoted text is the classic leak — if A quotes B, both documents contain B's words, and the model "discovers" they are the same person. Strip it.

**Alias redaction — required for the §11.2 blind claim to be true.** Removing the username from the *label* is not enough. Vendors sign posts with their handle, and PGP UIDs often contain it literally (`AngelEyes <...>`). If char n-grams read the handle out of the body text, the system is still matching a string. So at eval time, redact the alias and near-variants (case-insensitive, with `_`/`-`/digit-suffix variants, and leetspeak substitutions) from the body before vectorizing. `test_redaction.py` must assert this fires — right now the stage claim has no test behind it.

---

## 9. Temporal — `temporal/activity.py`
- Per alias: 24-bin hour-of-day histogram, plus 7-bin day-of-week, normalised.
- `S_time = 1 - JensenShannon(hist_A, hist_B)`.
- **Timezone estimate:** circular mean of posting hours → implied UTC offset → candidate region. This is a genuine step toward *real-world* identity and takes ten lines. Report it as a weak indicator with a stated confidence, never as a location claim.
- Aliases with <20 timestamped posts: set `S_time = NULL`, and have the fusion model handle missingness explicitly (impute to the corpus mean and add a `time_missing` indicator).

---

## 10. Fusion — learned, not hand-tuned

Features per alias pair: `[s_char, s_embed, s_hard, s_time, log1p(n_shared_hard)]`

```python
LogisticRegression(class_weight='balanced', C=1.0, max_iter=1000)
```

- Output is a **calibrated probability**, which is what an investigator can threshold on.
- The learned coefficients answer "why is hard evidence weighted more?" with a fitted number instead of an opinion. Print them on a slide.
- Fit takes seconds on CPU. This does not break the "no deep-model training" claim — it's a 5-parameter linear model.
- Keep `fusion/model.py --heuristic` as a fallback path with fixed weights `[0.25, 0.10, 0.45, 0.20]` in case the labelled set is too small.

Report **PR-AUC**, not accuracy. The classes are wildly imbalanced (almost no pair is a true match) and accuracy will read 99.9% while the system finds nothing.

**Split by alias, not by pair.** Train aliases ∩ test aliases must be empty. Splitting pairs randomly puts the same alias on both sides and leaks — the model memorises that alias's style instead of learning to compare. VeriDark uses disjoint author sets for exactly this reason. An ML-literate judge asks this immediately after "what's your baseline."

---

## 11. Evaluation — the section that decides whether judges believe you

### 11.1 Ground truth without planting anything
Same username appearing on two different marketplaces is the label. `Nightcrawler` on SilkRoad1 and `Nightcrawler` on Agora → positive pair. Negatives: random cross-market pairs, plus **hard negatives** — different aliases from the same market and same product category (this is where a topic-only model fails, and where char n-grams should win).

### 11.2 The blind protocol (mandatory — say this on stage)
At scoring time the username is **removed**. The model sees two anonymous bags of posts. If it recovers the pairing, that's real attribution. If we left the username in, we'd be matching a string, and a sharp judge will ask.

### 11.3 Stated caveat, delivered before anyone asks
Same handle across markets is a **labelling heuristic**, not proof of same person — handle squatting and post-SR1 impersonation are documented. We use it because it's the best free label available, and we say so. Volunteering the limitation is what makes the number credible.

### 11.4 Three edge-case tests (each gets a slide)
1. **False positive / hard negative:** two vendors, same market, same product, similar register, no shared hard evidence → must score low. Correct rejection is stronger evidence of rigour than any successful match.
2. **Sparse evidence:** alias with <10 posts → must return low confidence with `reason = "insufficient data"`, never a forced match.
3. **Adversarial style:** take one alias's posts, machine-paraphrase half, treat as a separate alias → show how much S_char degrades, and show S_hard still carries the link. This is the honest answer to "what if they change how they write?"

### 11.5 Report
`fusion/evaluate.py` emits precision, recall, F1, PR-AUC, a PR curve PNG, and a confusion matrix at the chosen threshold. Commit the output. Judges ask for numbers; have the file open.

---

## 12. Capability #1 — OpSec leak scanner (the differentiator)

Two halves. Build both.

### 12.1 Our own misconfigured hidden service — `opsec/demo_target/`

No dual boot, no VM, no Tails. Tor is a normal Windows program.

1. Download the **Tor Expert Bundle** from torproject.org (not Tor Browser — we need plain `tor.exe`).
2. `torrc`:
   ```
   HiddenServiceDir C:\tor-hs\demo
   HiddenServicePort 80 127.0.0.1:8080
   ```
3. Run `tor.exe`. It writes `C:\tor-hs\demo\hostname` containing our `.onion`.
4. Serve on `127.0.0.1:8080` — plain Flask app in `demo_target/`, no Apache needed.

**The attack chain — this is the headline, memorise it:**

```
hidden service leaks a CLEARNET REFERENCE  →  clearnet domain  →  CT pivot  →  operator's other infrastructure
```

Every link is documented in real de-anonymization work, and the leak step is the one operators fail at most often.

**Do not headline the TLS-cert path.** Hidden services almost never serve TLS — the onion address *is* the public key, so TLS is redundant and CA-issued certs for `.onion` are a rare EV-only edge case. Our demo target can serve one, but an NTRO evaluator may know this and call the scenario staged. Keep the cert-SAN detector as **one detector among several**, not the money shot. The clearnet-reference leak is the credible headline, and it feeds §12.2 identically.

Planted misconfigurations, each a detector in `scanner.py`:

| Misconfig | Detection | What it leaks |
|---|---|---|
| Clearnet resource referenced in HTML (`<img src="https://realsite.com/...">`, analytics, favicon, external CSS) | parse `src`/`href` | **Operator's clearnet domain — headline path into §12.2** |
| Exposed `/server-status` | GET, look for `Server at <host>` | Real hostname + IP |
| `.git/config` reachable | GET, parse `[remote "origin"]` url | Repo URL → often the operator's clearnet host or GitHub identity |
| `/.env`, `/backup.zip`, `/config.php.bak` reachable | GET, check status | Credentials, DB host, real domain |
| Directory listing on | `<title>Index of /</title>` | Filesystem paths, usernames |
| `Server:` / `X-Powered-By` headers | header read | Software + sometimes hostname |
| Default page left in place | hash against known defaults | Fingerprints the stack |
| TLS cert whose SAN contains a clearnet domain (rare on onions — supporting detector, not the demo's centrepiece) | parse cert, read SAN | Clearnet domain |

**Also run the same detectors over the corpus**, not just the demo target — the archives contain the markets' own leaked clearnet references (verified: one sampled post links out to a clearnet domain and even tags it `***clearnet***`). That connects capability #1 to the real data instead of leaving it a toy.

### 12.2 Certificate Transparency pivot — `opsec/ct_pivot.py`

Given a clearnet domain or a cert fingerprint from 12.1, find every other domain sharing that certificate — that's the operator's other properties.

**API — verified working 27 Aug 2026:**
```
https://api.certspotter.com/v1/issuances?domain=<d>&include_subdomains=true&expand=dns_names&expand=issuer
```
Returns JSON array; fields confirmed live: `id`, `tbs_sha256`, `cert_sha256`, `dns_names[]`, `issuer{name, friendly_name, pubkey_sha256}`, `not_before`, `not_after`, `revoked`.

Pivot logic: domain → certs → `dns_names[]` → **other domains on the same cert** → recurse one level. Also pivot on `pubkey_sha256` (same key reused across certs = same operator, stronger than a shared name).

**crt.sh is the fallback, not the primary.** It returned `502 Bad Gateway` on three separate attempts during this research session. `https://crt.sh/?q=<domain>&output=json`.

**Non-negotiable: cache every response to `data/cache/ct/<sha256(query)>.json`.** The demo replays from cache by default; `--live` re-queries. Never put a flaky third-party API on the critical path of a live stage demo. certspotter's unauthenticated rate limit is tight — the cache also keeps you under it during development.

---

## 13. Graph — `graph/build.py`
- Requires an open `case_id` (§6.2). Edges are drawn from `pair_scores` **for that case** where `confidence ≥ cases.threshold` (or the threshold recorded on the case row).
- Node = alias (`market:alias`). Edge weight = confidence.
- **Connected components** = candidate actor clusters. Persist membership into the `clusters` table keyed by `(case_id, cluster_id, alias_id)`.
- Report per cluster: markets spanned, date range, total posts, all shared hard evidence, **degree + betweenness centrality** to surface the core alias (the persona that bridges markets — usually the actor's primary identity).
- Cross-market edges get a distinct colour in the render. That's the visual the judges remember: one node in SilkRoad1 wired to a node in Agora wired to a node in Evolution.
- Render with `pyvis` → standalone HTML, opens in a browser, no server. Physics off after layout settles or the graph wobbles during the pitch.
- When showing shared hard evidence for a cluster, join through `evidence.post_id` → `posts` and expose source lineage (`source_archive`, `scrape_date`, `source_member_path`, `content_sha256`) so the forensic chain stops at the archive member, not at the evidence row.

### 13.1 Neo4j projection — `graph/neo4j_sink.py`

**networkx stays the compute engine.** Components, centrality, thresholding — all in-process, all offline. Neo4j receives the **finished** graph. Nothing in the attribution path depends on a server being up.

What it earns:
- **Ad-hoc Cypher in front of an investigator.** This is the real reason. An analyst asks a question nobody anticipated, and it's answered in one query instead of a code change. PS asks for "query capabilities" — this is the strongest possible answer to that line.
- **Neo4j Browser visualisation.** Expand a node, walk the neighbourhood interactively. Better on stage than a static pyvis render, because the judge can drive it.
- **Multi-user.** Several investigators query one graph; SQLite + in-process networkx can't do that.
- **Scale story that isn't hypothetical.** "Graph exceeds RAM" stops being a slide and becomes a wired path.

**Install:** Neo4j Community Edition, zip or Desktop (JVM bundled). No Docker. Free, no licence. Default bolt `bolt://localhost:7687`.

**Model:**
```cypher
(:Alias {name, market, n_posts, first_seen, last_seen, is_vendor, centrality})
(:Actor {cluster_id, n_aliases, markets, max_confidence})
(:Evidence {kind, value})          // kind: pgp_fpr | btc | onion | clearnet | email
(:Domain {name, source})           // clearnet domains from §12

(:Alias)-[:MEMBER_OF]->(:Actor)
(:Alias)-[:LINKED_TO {confidence, s_char, s_embed, s_hard, s_time, cross_market}]->(:Alias)
(:Alias)-[:USED {n_posts, first_seen}]->(:Evidence)
(:Evidence)-[:PIVOTS_TO]->(:Domain)     // CT-log siblings from §12.2
```

**Load:** batched `UNWIND` + `MERGE`, 5k rows per transaction. Uniqueness constraints on `Alias(market,name)` and `Evidence(kind,value)` before loading, or MERGE degrades to a full scan and a 50k-node load takes minutes instead of seconds.

```python
# neo4j==6.2.0
from neo4j import GraphDatabase
driver = GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", pw))
```

**Cypher queries to have ready on stage** — these are the demo, not the schema:
```cypher
// actors spanning three or more markets, ranked
MATCH (a:Alias)-[:MEMBER_OF]->(act:Actor)
WITH act, collect(DISTINCT a.market) AS mkts
WHERE size(mkts) >= 3
RETURN act.cluster_id, mkts, act.max_confidence ORDER BY act.max_confidence DESC;

// shortest evidence path between two aliases — "how are these two connected?"
MATCH p = shortestPath((a:Alias {name:$a})-[:USED|LINKED_TO*..6]-(b:Alias {name:$b}))
RETURN p;

// one wallet, many aliases — shared-infrastructure hotspots
MATCH (e:Evidence {kind:'btc'})<-[:USED]-(a:Alias)
WITH e, count(DISTINCT a) AS n WHERE n > 1
RETURN e.value, n ORDER BY n DESC LIMIT 20;

// onion leak → clearnet domain → operator's siblings (capability #1 as a graph walk)
MATCH (a:Alias)-[:USED]->(e:Evidence {kind:'clearnet'})-[:PIVOTS_TO]->(d:Domain)
RETURN a.name, a.market, e.value, collect(d.name);
```

That last query is worth rehearsing — it renders the whole de-anonymization chain as one picture.

**Guardrails:**
- Sink runs **after** `graph/build.py` and is skippable via `--no-neo4j`.
- **Two profiles in `config.yaml`:** `dev` has the sink off (no server needed while iterating); `demo` has it **on**. The stage runs the `demo` profile. `--no-neo4j` is the panic switch, not the demo state — get this backwards and the Browser is empty in front of the judge.
- Load is idempotent (MERGE), so a failed load is re-runnable mid-demo.
- Neo4j down → pyvis render and every export in §15 still work. Test that path.
- Read-only user for the query console and for the agent tool below. The pipeline's writer credentials never reach the UI.

**Agent tool (§16.2 gains a seventh):**
```python
@tool
def cypher_query(question_cypher: str) -> list[dict]:
    """Run a READ-ONLY Cypher query against the actor graph. Rejects CREATE/MERGE/DELETE/SET."""
```
Reject writes by regex **and** connect with a read-only Neo4j user — the regex is a courtesy, the user account is the control.

> **Verify at step 14, before step 15 depends on it:** creating a read-only user needs `CREATE USER … SET PASSWORD …` + `GRANT ROLE reader`, and **Community Edition's RBAC is limited compared to Enterprise** — the role grant may not be available. If it isn't, fall back to a separate database with no write path wired into the UI, and state the limitation rather than claiming an enforcement you don't have. Note that `test_cypher_readonly.py` tests the regex and passes either way, so it will **not** catch this. Also confirm `neo4j==6.2.0` driver compatibility against whichever Community server version you install. With this, the investigator agent can answer graph-shaped questions no pre-written tool covers. That combination — natural-language question → generated Cypher → graph answer with evidence shown — is the most impressive thing in the whole demo.

`langchain-neo4j==0.10.0` provides a prebuilt Cypher chain. Try it, but keep the hand-written tool: a chain that generates wrong Cypher on stage is worse than six reliable tools.

---

## 14. Explanation — `explain/reason.py` + `explain/trail.py`
This is the start of the **Evidence / Investigation** layer (§1): not a new score, but the answer to *why believe this*, *what was observed*, and (with UI/agent/Cypher) *what to check next*.

**Template-first prose (`reason.py`).** The evidence is already structured; a template produces a correct, fast, offline, deterministic sentence:

> `Alias_A` (SilkRoad1, 214 posts) and `Alias_C` (Agora, 88 posts) — **confidence 0.91**. Shared PGP fingerprint `A1B2…9F0` in 3 posts. Shared BTC address `1FTYtw…4PSK`. Stylometric similarity 0.74 (char n-gram). Posting-hour overlap 0.81, both consistent with UTC+1.

Optional LLM polish via Ollama, using **the same `llm_model` from `config.yaml` as §16.2** — never a second model — takes the structured evidence dict and rewrites it as an investigator's paragraph. **The LLM never sees raw posts and never decides anything.** It rewrites facts the pipeline already computed. Say that explicitly when a judge asks whether the AI is hallucinating attributions.

If Ollama isn't running, fall back to the template silently. Do not let a model download failure break the demo.

**Evidence Trail (`trail.py`).** Separately from prose, build the ordered step list defined in §15. The template sentence is what you *read*; the trail is what you *show*. Both must agree with the same underlying rows. The trail never invents steps; OpSec/CT nodes appear only when the active case has matching findings.

---

## 15. UI and exports — the free marks

**`ui/app.py` — Streamlit** (single file, no frontend build, runs `streamlit run`). Page title / sidebar brand: **SUTRANETRA**; optional subtitle with the tagline. Never ship the old working title in the chrome.
1. **Case selector** — pick an active `case_id`; show corpus snapshot, model version, threshold, config hash, status. All other views are scoped to that case.
2. **Search** — alias, wallet, PGP fingerprint, onion, clearnet domain. Full-text over `evidence` + `posts`. Hit rows must show post source lineage (archive / scrape date / member path / content hash).
3. **Actor cluster view** — cluster list for the active case, sorted by confidence; click → member aliases, evidence table **with provenance**, embedded pyvis graph.
4. **Pair inspector** — two aliases side by side, per-feature score breakdown from `pair_scores` for this case, the shared-evidence rows with surrounding context **and source lineage**, and the generated explanation.
5. **Evidence Trail** — the headline investigation view. Given a cluster or a pair under the active case, render a **vertical ordered chain** that answers *"How did your system reach this conclusion?"* without requiring the judge to join tables mentally. Built by `explain/trail.py` (deterministic; no LLM). Typical shape:

```
Alias A (SilkRoad1)
   ↓
Post #1234  ·  silkroad1-forums.tar.xz / 2014-11-25 / <member path>
               content_sha256=a3f1…
   ↓
PGP fingerprint X   (evidence row → post lineage)
   ↓
Alias B (Agora)
   ↓
Post #9812  ·  agora-forums.tar.xz / … / …
   ↓
Shared wallet Y
   ↓
Fused confidence 0.91   (S_char / S_embed / S_hard / S_time breakdown)
   ↓
Clearnet domain Z       (opsec finding or corpus clearnet evidence)
   ↓
CT certificate …
   ↓
Sibling domain Q
```

Each step is a typed node (`alias` | `post` | `evidence` | `score` | `opsec` | `ct_cert` | `ct_domain`) with the underlying row ids so the same trail can be exported and queried by the agent. Missing branches (no OpSec hit for this cluster) are omitted rather than fabricated — never invent a trail step.
6. **OpSec scan tab** — run the scanner against a target, show findings + the CT pivot results as a small graph; findings write to `opsec_findings` under the active case.
7. **Export buttons** on every view.

**`explain/trail.py`:**
```python
def build_evidence_trail(db, case_id: str, *, cluster_id: int | None = None,
                         a_alias_id: int | None = None, b_alias_id: int | None = None
                         ) -> list[dict]:
    """Return ordered trail steps for UI / JSON / agent. Deterministic. No LLM."""
```
Prefer the strongest hard-evidence path between the two highest-centrality (or selected) aliases in a cluster, then append fused confidence, then any case-scoped OpSec/CT steps linked to those aliases' clearnet evidence. Source lineage from §6.1 must appear on every `post` step.

**`export/writers.py`** (always keyed by `case_id`):
- `clusters.csv` — case_id, cluster_id, alias, market, n_posts, confidence, evidence_summary
- `report.json` — full nested structure: case metadata → clusters → aliases → evidence → **post provenance** → per-feature scores → **evidence_trail[]** → explanation → opsec findings. A downstream reader must reconstruct `cluster → pair → evidence → post → archive member` (and CT pivot when present) without the live DB.
- `report.pdf` — ReportLab: cover (including case card), methodology, per-cluster page with graph image + evidence table + **Evidence Trail** + provenance + explanation, ethics statement, eval metrics appendix. Set `cases.report_path` when written.

PS names CSV, JSON and report generation explicitly. Half a day of work. Don't skip it. The Evidence Trail is the single best UI element for a forensics pitch — if time forces a cut inside §15, cut polish on PDF before cutting the trail.

---

## 16. Agentic layer — LangChain + LangGraph

Two separate uses. One is orchestration, one is a real agent. Both are in scope; they are not the same thing and should not be built at the same time.

**Package versions (checked on PyPI 27 Aug 2026 — pin these):**
```
langgraph==1.2.11
langchain==1.3.17
langchain-core==1.6.0
langchain-ollama==1.1.0
langgraph-checkpoint-sqlite==3.1.1
```
LangChain 1.x renamed things versus the 0.x tutorials all over the internet. Before writing agent code, run `python -c "import langchain.agents as a; print(dir(a))"` and build against **the installed API**, not against a blog post. This is the single biggest time sink in this section.

### 16.1 Pipeline orchestration — LangGraph `StateGraph`

Wrap the six stages as nodes over one typed state object.

```python
# src/pipeline/graph.py
from typing import TypedDict
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.sqlite import SqliteSaver

class CaseState(TypedDict):
    case_id: str                 # must equal cases.case_id (§6.2)
    markets: list[str]
    n_posts: int
    n_aliases: int
    n_evidence: int
    candidate_pairs: int
    scored_pairs: int
    clusters: list[dict]
    opsec_findings: list[dict]
    errors: list[str]

g = StateGraph(CaseState)
g.add_node("ingest",     node_ingest)      # wraps ingest/load.py
g.add_node("evidence",   node_evidence)
g.add_node("stylometry", node_stylometry)
g.add_node("fusion",     node_fusion)
g.add_node("graph",      node_graph)
g.add_node("opsec",      node_opsec)
g.add_node("explain",    node_explain)

g.add_edge(START, "ingest")
g.add_edge("ingest", "evidence")

# opsec does not depend on fusion — genuine parallel branch, joined at explain
g.add_edge("evidence", "stylometry")
g.add_edge("evidence", "opsec")
g.add_edge("stylometry", "fusion")
g.add_edge("fusion", "graph")
g.add_edge("graph", "explain")
g.add_edge("opsec", "explain")     # explain waits for both branches
g.add_edge("explain", END)

app = g.compile(checkpointer=...)   # see note below
```

**Unverified against the installed version — do not copy blindly.** In recent LangGraph, `SqliteSaver.from_conn_string()` is a **context manager**, not a plain constructor; assigning it bare hands you a CM object, not a saver. Step 13's first action is confirming the checkpointer's construction contract in the installed package, then writing this line.

**Hard rule: every node is a thin wrapper.** `node_evidence(state)` calls `evidence.extract.run(db)` and returns counts. Zero business logic inside a node. Every stage must still run standalone from the CLI (`python -m src.evidence.extract`). Test that. If the framework misbehaves the night before the demo, you delete `pipeline/graph.py` and lose nothing but the wrapper.

**Case lifecycle in the wrapper.** On START, ensure a `cases` row exists for `state["case_id"]` (create via `pipeline/case.py` if needed) and set `status='running'`. On END after explain, set `status='complete'` (or `failed` if `errors` is non-empty) and refresh `corpus_snapshot` counts if ingest ran in this session. Scoring nodes write `pair_scores` / `clusters` / `opsec_findings` only under that `case_id`.

**What this genuinely buys you** (say these, not "we used LangGraph"):
- **Checkpoint + resume.** `SqliteSaver` persists state per node. Ingest of 5 markets takes ~40 min; a crash at fusion resumes from the checkpoint instead of re-ingesting. Real, demonstrable, and worth showing.
- **Parallel branch.** `opsec` does not depend on `fusion`. Fan it out from `evidence` and join before `explain` — genuinely concurrent, and the graph makes it one line instead of a threading rewrite.
- **A rendered pipeline graph.** `app.get_graph().draw_mermaid_png()` → put it straight in the deck. That's your architecture diagram, generated from the code that actually runs, which is a stronger claim than a hand-drawn box diagram.

### 16.2 Investigator agent — LangChain tool-calling (the part judges remember)

This is where an agent earns its place. Not in the scoring path — in the **query** path. PS asks for "contextualisation and query capabilities". A natural-language investigator console is exactly that, and it's a live demo moment.

```python
# src/agent/investigator.py
from langchain_core.tools import tool
from langchain_ollama import ChatOllama

@tool
def search_evidence(kind: str, value: str) -> list[dict]:
    """Find every alias linked to a wallet, PGP fingerprint, onion or clearnet domain."""

@tool
def get_cluster(alias: str, market: str) -> dict:
    """Return the actor cluster containing this alias: members, markets, confidence, shared evidence."""

@tool
def score_pair(alias_a: str, market_a: str, alias_b: str, market_b: str) -> dict:
    """Return the stored per-feature scores and fused confidence for a pair. Read-only."""

@tool
def evidence_trail(case_id: str, cluster_id: int | None = None,
                   alias_a: str | None = None, market_a: str | None = None,
                   alias_b: str | None = None, market_b: str | None = None) -> list[dict]:
    """Return the ordered Evidence Trail for a cluster or pair (§15). Read-only; calls explain.trail."""

@tool
def get_case(case_id: str) -> dict:
    """Return case metadata: corpus snapshot, config hash, model version, threshold, status."""

@tool
def alias_timeline(alias: str, market: str) -> dict:
    """Posting activity over time, hour-of-day histogram, estimated UTC offset."""

@tool
def ct_pivot(domain: str) -> list[str]:
    """Certificate Transparency pivot: sibling domains sharing a cert or public key. Cache-first."""

@tool
def opsec_scan(target_url: str) -> list[dict]:
    """Run the misconfiguration scanner against a target. Localhost/demo targets only."""
```

Model: `ChatOllama(model=cfg.llm_model, temperature=0)` — local, free, offline, no API key. Tool-calling works on 8B; if RAM is tight use `qwen2.5:7b`, stronger at tool selection than any 3B.

**One model serves both this and §14.** The model name lives in `config.yaml` as `llm_model` and §14 reads the same key. Two different models resident at once is an out-of-memory failure on an 8 GB laptop, and it will happen on demo day if the setting is duplicated.

Demo queries that land:
- *"Which aliases used the same PGP key as Nightcrawler on Agora?"*
- *"Show me actors active on both SilkRoad1 and Evolution with confidence above 0.8."*
- *"This vendor's forum leaked a clearnet domain — what else does that operator run?"* (chains `search_evidence` → `ct_pivot`, two tools in one turn, visibly)
- *"Walk me through the evidence trail for cluster 17 on CASE-2026-001."* (calls `evidence_trail`)

### 16.3 Guardrails — non-negotiable, and they are a selling point

1. **The agent never computes a verdict.** Every tool is read-only over `pair_scores` and `evidence`. It retrieves and phrases; the deterministic pipeline decides. `opsec_scan` is the only tool with side effects and it is whitelisted to localhost / explicitly-supplied demo targets.
2. **No tool writes to the DB.** Enforce with a read-only SQLite connection (`file:attrib.sqlite?mode=ro`) in the agent process. Not a convention — a connection flag.
3. **Every answer carries provenance.** Tools return row ids; the UI renders the underlying evidence rows beneath the agent's text. Judge can always see the source.
4. **Agent offline → console degrades to structured search.** The Streamlit filters in §15 stay fully functional with Ollama dead. Test that path.

This is the answer to "is your AI hallucinating attributions?":

> "The LLM has no access to the scoring path. It queries results the deterministic pipeline already produced, and every sentence it writes is backed by evidence rows shown underneath it. Attribution is reproducible; the language around it is generated."

For a forensics tool shown to NTRO, that framing is stronger than autonomy. Non-deterministic attribution is not usable as evidence.

### 16.4 Build order for this section

Build **after** step 11. The agent is a layer over a working system; there is nothing to query until the pipeline produces clusters.

1. §16.1 wrapper — half a day, low risk, gives checkpointing + the generated diagram
2. §16.2 tools — each tool is a thin call onto a function that already exists from steps 3–9
3. §16.3 guardrails + the offline fallback path
4. Rehearse three agent queries until they cannot fail. Cache/pin the model locally; do not download a model on demo day.

---

## 17. Build order

Each step ends with something runnable. Don't proceed on a broken step.

| # | Step | Done when |
|---|---|---|
| 1 | `fetch.py` + `smf_parser.py` on `cannabisroad3` (2.2 MB) | posts populated **with source lineage**, dedupe verified, spot-check 5 posts against HTML by eye |
| 2 | Scale to `nucleus`, then SR1 + Agora + SR2 + Evolution + TheHub | ≥1 M posts, ≥5 markets, `aliases` table built; lineage non-null on all rows |
| 3 | `evidence/` — PGP, BTC (with base58check test), onion, clearnet | evidence table populated; count hits per kind and eyeball 10 |
| 4 | Cross-market label set (§11.1) | N positive pairs + hard negatives, stored with `label` |
| 5 | `char_ngram.py` + blocking | S_char for all candidate pairs |
| 6 | `embed.py`, `activity.py` | S_embed, S_time |
| 7 | `pipeline/case.py` + `fusion/` + `evaluate.py` | **case row created**; `pair_scores` case-scoped; **PR-AUC number exists** |
| 8 | `graph/build.py` + pyvis | clusters persisted for the case; cross-market clusters render |
| 9 | **`opsec/` — demo target + scanner + CT pivot** | findings stored under case_id; scanner outputs a real clearnet domain |
| 10 | `explain/reason.py` + `explain/trail.py` | readable sentence **and** ordered Evidence Trail per cluster/pair |
| 11 | `ui/` + `export/` | case selector, **Evidence Trail tab**, CSV/JSON/PDF with provenance |
| 12 | Edge-case tests (§11.4), ethics doc | three slides with real numbers |
| 13 | **§16.1 LangGraph wrapper** — thin nodes over existing functions | pipeline runs end-to-end through `StateGraph`; case lifecycle wired; kill mid-run, resume from checkpoint; `draw_mermaid_png()` |
| 14 | **§13.1 Neo4j sink** — project the finished graph | four rehearsed Cypher queries return correct results in Neo4j Browser; `--no-neo4j` still produces the full pyvis + export path |
| 15 | **§16.2 investigator agent** + §16.3 guardrails + `cypher_query` + `evidence_trail` tools | NL queries answered with provenance; Evidence Trail tool works; read-only SQLite + Neo4j verified |
| 16 | Ollama explanation polish (§14) | optional |

Step 9 is the differentiator. Do not let it slip to last — if time runs out, a working leak scanner with weaker stylometry beats perfect stylometry with no capability #1.

---

## 18. Tests — `tests/`

Minimum set. Each one fails loudly if the logic breaks:

- `test_smf_parser.py` — one saved HTML fixture, assert exact alias/ts/msg_id/body **and** that lineage fields are populated when the loader supplies archive/scrape/member
- `test_dedupe.py` — same thread from 4 scrape dates → post count unchanged; **winning row's `scrape_date` / `source_member_path` / `content_sha256` match the newest scrape**
- `test_post_provenance.py` — every fixture post has non-null `source_archive`, `scrape_date`, `source_member_path`, `content_sha256`; recomputing sha256 from stored `raw_html` matches; evidence→post join returns archive member fields
- `test_cases.py` — create two cases with different thresholds; `pair_scores` / `clusters` for case A are invisible to case B; status transitions `created→running→complete`; `config_hash` is stable for identical canonical config
- `test_crypto_addr.py` — the 4 real BTC addresses found in the sample pass; the MD5 hash `16936e5adb8a36cbb21d38beeb6f8e11` and short string `3y4kBQhzP5dPh1AiMhNWU7HKLB3` fail
- `test_pgp.py` — armored block → known fingerprint
- `test_fusion.py` — shared PGP alone pushes confidence above threshold; identical topic with zero hard evidence stays below
- `test_redaction.py` — a post signed `- AngelEyes` and a PGP UID containing the handle both come back with the alias removed (§8.4)
- `test_ct_pivot.py` — cached JSON fixture → expected domain set (no network in tests)
- `test_scanner.py` — spin the demo target, assert every planted misconfig is detected
- `test_evidence_trail.py` — synthetic case with two aliases, shared PGP on known posts, fused score, and a clearnet→CT stub: `build_evidence_trail` returns ordered steps of the expected types; every `post` step includes source lineage; no fabricated OpSec steps when none exist
- `test_no_framework_leak.py` — walk every `.py` under `src/`, parse its imports with `ast`, assert nothing outside `src/pipeline/` and `src/agent/` imports `langchain`/`langgraph`, and nothing outside `src/graph/neo4j_sink.py` and `src/agent/` imports `neo4j`. Ten lines, no environment manipulation. **This test is what makes the "wrapper, not owner" claim in §13.1 and §16 true** — without it the claim is an intention
- `test_cypher_readonly.py` — `cypher_query` rejects `CREATE`/`MERGE`/`DELETE`/`SET`/`DROP` including mixed case and leading whitespace
- `test_agent_readonly.py` — every tool in `agent/tools.py` holds a `mode=ro` connection; a write attempt raises

Pytest, no fixtures framework, no mocking library. Fourteen files (minimum).

---

## 19. Demo script (~8 min — **check your actual slot first**, SIH pitches are often 6–8 min plus Q&A, and rehearsing to the wrong length is the classic own goal)

**Compression order, decided now and not on stage:**
1. **Never cut:** step 6, capability #1. It is the differentiator.
2. **Never cut:** the Evidence Trail handoff in step 4b — it is the visual answer to "how did you reach this?"
3. **Never cut:** the Cypher / Neo4j Browser handoff in step 7 — letting a judge drive the graph themselves is the moment they remember.
4. **First to go:** the natural-language agent query in step 7. Drop straight to Evidence Trail + Cypher and the pitch still lands.
5. **Second to go:** step 3's live pipeline run — switch to pre-computed results.


1. **Frame it (30 s).** Open on the name: **SUTRANETRA** — *"The eye that follows the hidden threads."* One breath on etymology (*sutra* / *netra*), then: "Alias clustering tells you two nicknames are one person. It doesn't tell you who. We follow the thread outward — and that second half is what NTRO actually asked for."
2. **Corpus (30 s).** 5 markets, 2011–2015, public archive. State the legal position in one sentence and move on.
3. **Run the pipeline (90 s).** Live. Open case card (`CASE-2026-001`). Graph renders. Cross-market cluster lights up — one actor across SilkRoad1, Agora and Evolution.
4. **Explain (20 s).** Read the generated reason aloud: shared PGP fingerprint, shared wallet, 0.74 stylometric, UTC+1 activity.
4b. **Evidence Trail (40 s).** Switch to the Evidence Trail tab. Walk the vertical chain: Alias A → Post (archive/scrape/path/hash) → PGP → Alias B → Post → wallet → confidence 0.91 → clearnet → CT → sibling domain. *"That is the forensic chain — not a black-box score."*
5. **Show the rejection (50 s).** Two aliases, same market, same product, high topical similarity — system correctly did **not** link them, and says why. *"Anything can find matches. Being right about non-matches is the harder half."*
6. **Capability #1 (100 s).** Switch to the OpSec tab. Scan the hidden service. It leaks a clearnet reference — `/server-status` gives the real hostname, and the page pulls an image from the operator's real domain. Take that domain, pivot through CT logs, land on the operator's sibling infrastructure. *"That's a real-world artifact. That's the difference between correlation and de-anonymization."* Show the same CT step appear at the bottom of the Evidence Trail.
7. **Investigator agent + Cypher (75 s).** Type a plain-English question into the console — *"walk me through the evidence trail for this cluster"* or *"this vendor leaked a clearnet domain, what else does that operator run?"* — evidence rows / trail steps rendering underneath. Then hand the judge Neo4j Browser and run the leak→domain→siblings Cypher from §13.1 so they can expand nodes themselves. Say the guardrail line from §16.3 before anyone asks it.
8. **Numbers + limits (60 s).** PR-AUC, blocking recall, the adversarial-paraphrase degradation curve, the handle-squatting caveat. Then scaling: FAISS → Milvus, single-file SQLite → Postgres, batch → continuous collection.

Rehearse step 6 until it can't fail. Cache everything it touches.

---

## 20. Environment

**Python 3.11** (3.12 is fine; `sentence-transformers` wheels are most reliable on 3.11).

```
beautifulsoup4>=4.12
lxml>=5.0
pandas>=2.2
scikit-learn>=1.5
sentence-transformers>=3.0
faiss-cpu>=1.8
networkx>=3.3
pyvis>=0.3.2
pgpy>=0.6.0
base58>=2.1
requests>=2.32
streamlit>=1.38
reportlab>=4.2
matplotlib>=3.9
pytest>=8.0
scipy>=1.14

# agentic layer (§16) — pin exactly, LangChain 1.x renamed 0.x APIs
langgraph==1.2.11
langchain==1.3.17
langchain-core==1.6.0
langchain-ollama==1.1.0
langgraph-checkpoint-sqlite==3.1.1

# graph projection (§13.1) — optional at runtime
neo4j==6.2.0
langchain-neo4j==0.10.0
```

Install the optional layers **in a separate step, after the core pipeline works**. They pull large dependency trees and a resolver conflict must never be able to break ingestion.

**Neo4j Community Edition** is a separate download (zip or Desktop, JVM bundled, free, no licence, no Docker). Server needs ~2 GB RAM while running — budget it alongside the Ollama model, and don't run a graph load and an LLM query at the same moment on an 8 GB laptop.

No GPU. No paid API. No account signup anywhere in the stack. Total cost: ₹0.

Disk: ~4 GB archives + ~2 GB SQLite + ~400 MB sentence-transformers + ~4.7 GB Ollama model. **Keep 15 GB free.**

---

## 21. Do NOT build

Auth/login, multi-tenancy, CI/CD, Docker, monitoring, alerting, autoscaling, REST API, real-time streaming ingestion, custom frontend framework, a message queue.

None of it is judged. None of it demonstrates whether the attribution mechanism works. Every hour spent there is an hour not spent on capability #1.

---

## 22. Risks and mitigations

| Risk | Mitigation |
|---|---|
| A market's HTML doesn't match the SMF parser | Start with the verified `cannabisroad3` layout. Add `phpbb_parser.py` only when a specific market fails. Skip a market rather than block — five markets is plenty |
| Too few cross-market same-username pairs | Add TheHub (cross-market meta-forum, highest overlap by construction). If still thin, add same-market temporal splits as a secondary label source |
| Embedding pass too slow on the full corpus | Cap at 200 posts per alias (sampled), and run char n-grams on everything — char n-grams are cheap and carry the style signal anyway |
| certspotter rate-limits or crt.sh is down mid-demo | Cache-first by default. Live query behind `--live`. Verified failure mode: crt.sh returned 502 three times during research |
| Ollama model won't load on the demo machine | Template explanations are the default path; LLM is polish. Test the fallback. Pull the model days early — never download on demo day |
| LangChain 1.x API differs from every 0.x tutorial online | Pin the five versions in §20, and build against `dir()` of the installed package, not a blog post. Budget half a day for this alone |
| Agent picks the wrong tool or loops | `temperature=0`, ≤6 tools, tool docstrings written as instructions. Cap iterations. Rehearsed queries are the demo path; free-form is the bonus |
| Agentic dependency tree breaks the core install | Install core first, optional layers second, in a separate step. Core pipeline must import and run with LangChain and the neo4j driver uninstalled |
| Neo4j server won't start on demo day (JVM, port 7687 taken, heap) | `--no-neo4j` is the default in `config.yaml`. Every §15 export and the pyvis render work without it. Start the server **before** the pitch, not during. Have a screen recording of the Cypher queries as a last resort |
| Neo4j + Ollama + Streamlit together exhaust 8 GB RAM | Don't run a graph load and an LLM query concurrently. Load Neo4j once before the demo; the pitch only reads |
| Generated Cypher is wrong on stage | Rehearsed queries in §13.1 are the demo path. `langchain-neo4j`'s auto-generated Cypher is the bonus, shown only after the fixed ones land |
| Zenodo/VeriDark approval never arrives | It's already off the critical path. dnmarchives is primary |
| Judge asks "isn't matching usernames circular?" | §11.2 blind protocol — the username is stripped at scoring time. Have the code path ready to show |
