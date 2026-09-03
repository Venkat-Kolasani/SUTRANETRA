# Prompt 09 — OpSec leak scanner + Certificate Transparency pivot (the differentiator)

## Objective
This is the capability that separates this submission from a generic alias-clustering project — the one that produces a real-world artifact (a clearnet domain, a hostname, a piece of infrastructure) instead of just a correlation between two pseudonyms. Per `CLAUDE.md` §9, this is the **last thing to cut** under any time pressure. Build it early enough that it isn't the thing squeezed out if the schedule slips — the spec is explicit that a working leak scanner with weaker stylometry beats perfect stylometry with no leak scanner at all.

## Spec references
`SPEC.md` §12 (both subsections in full) — read this section more carefully than any other before starting.

## Preconditions
Prompt 03 (evidence extraction, specifically onion/clearnet detection) complete. This prompt does not strictly depend on Prompts 05–08, and can be built in parallel with them if useful — but it must be complete before Prompt 13 (LangGraph orchestration), since that step wires it in as a parallel branch.

## Detailed requirements

### 1. Our own misconfigured hidden service — `src/opsec/demo_target/`
Set up a real Tor hidden service under your own control, on your own machine, with no VM/dual-boot/Tails required:
- Download the Tor Expert Bundle (plain `tor.exe`/`tor` binary, not the Tor Browser bundle — you need the standalone daemon, not the browser).
- Configure it with a hidden-service directory and a single port mapping to a local Flask (or equivalent) app you write and control.
- Confirm the service comes up and its generated `.onion` hostname is reachable over Tor.
- The Flask app is your own — deliberately plant every misconconfiguration listed below into it. This is a controlled, self-authored target; nothing here touches any real or third-party hidden service, ever.

### 2. Planted misconfigurations — implement one detector per item, in `src/opsec/scanner.py`
Each of these is both a thing your demo target actually exposes, and a specific detector that finds it:
- **Clearnet resource referenced in the served HTML** (an image `src`, analytics snippet, favicon, or external stylesheet pointing at a real clearnet domain) — this is the headline path. Detecting it means parsing the served page's `src`/`href` attributes and flagging any that resolve to a non-onion, real-world domain. This is the leak that feeds directly into the CT pivot below, and the spec is explicit that this — not the TLS-certificate path — is the credible centerpiece to lead the demo with.
- **Exposed `/server-status`** — request it, and if reachable, extract the real hostname it discloses (`Server at <host>`).
- **Reachable `.git/config`** — request it, and if present, parse the `[remote "origin"]` URL, which often discloses the operator's real clearnet host or a source-control account identity.
- **Reachable `/.env`, `/backup.zip`, `/config.php.bak`** or similar — detect via HTTP status check; these commonly leak credentials or a real database host.
- **Directory listing left enabled** — detect via the presence of an `Index of /`-style page title, which discloses filesystem paths and sometimes usernames.
- **`Server:` / `X-Powered-By` response headers** — read directly; discloses the software stack and occasionally a hostname.
- **A default/stock page left in place** — fingerprint by comparing against known default-page content, which discloses the underlying software stack.
- **TLS certificate SAN containing a clearnet domain** — parse the certificate and read its Subject Alternative Names. Implement this detector, but **do not headline it in the demo materials**: hidden services almost never serve TLS in practice (the onion address itself already functions as the public key, so a CA-issued cert is a rare, EV-only edge case), and an evaluator who knows this may read a TLS-based demo scenario as staged. Keep it as one detector among several, feeding the same downstream pivot, not the lead example.

### 3. Run the same detector suite over the historical corpus, not only the demo target
This connects capability #1 to the real dataset instead of leaving it a standalone toy: run the clearnet-reference and onion-reference detectors over the ingested corpus's post bodies (reusing Prompt 03's onion/clearnet evidence extraction where applicable) and surface any clearnet domains the historical marketplace actors themselves leaked. The spec's own sample corpus contains a post explicitly self-tagged `***clearnet***` linking to a real clearnet domain — confirm your detector suite actually catches this kind of real, already-present leak in the data you ingested, not just in the synthetic demo target.

### 4. Certificate Transparency pivot — `src/opsec/ct_pivot.py`
Given a clearnet domain (from either source above) or a certificate fingerprint:
- Query the Cert Spotter API (`https://api.certspotter.com/v1/issuances`, with `domain`, `include_subdomains=true`, and `expand=dns_names`/`expand=issuer` parameters) to retrieve every certificate issuance touching that domain, and extract the `dns_names[]` list from each issuance — every other domain sharing a certificate with the target domain is a candidate piece of the same operator's infrastructure.
- Also pivot on `pubkey_sha256` — the same public key reused across multiple certificates is a **stronger** signal of common ownership than merely sharing a domain name on one cert, since key reuse reflects the same underlying server/operator rather than just a multi-domain certificate.
- Recurse one level: take the newly discovered sibling domains and pivot on them too, to surface a small neighborhood of an operator's infrastructure rather than just the immediate result.
- Treat `crt.sh` (`https://crt.sh/?q=<domain>&output=json`) as a fallback only, not the primary source — it is known to return intermittent server errors, and the spec's own research session hit exactly that failure during preparation.
- **Register a free Cert Spotter API key** (per `docs/VALIDATION-AND-NOVELTY.md` §3) and support supplying it via an environment variable or config value, used when present; the unauthenticated tier is fine for light development use but should not be assumed reliable under repeated calls during a demo rehearsal week.

### 5. Cache-first, always
Cache every CT API response to `data/cache/ct/<hash-of-query>.json`. The demo replays from this cache by default; a live re-query only happens behind an explicit `--live` flag. This is non-negotiable — a flaky third-party API must never sit on the critical path of a live stage demo. Populate the cache ahead of time for whatever domains you intend to actually demo, and rehearse against the cached path, not the live one.

### 6. Persist findings under a case
Every scanner/CT result that should appear in the Evidence Trail or exports must be written to `opsec_findings` with a `case_id` (`SPEC.md` §6.2). CLI accepts `--case-id` (create/open via `pipeline/case.py` if needed). Standalone exploratory scans without a case are fine for debugging, but the demo path and UI path always write under a case.

## Explicit constraints & known gotchas
- Never scan, probe, or otherwise interact with any real, third-party, or live hidden service. The only scan target in this entire project is the one you built yourself in step 1.
- Do not lead the pitch, the UI, or the report copy with the TLS-certificate detector — see the explicit reasoning in step 2 above. Lead with the clearnet-resource-reference leak.
- If Cert Spotter rate-limits during development, that is exactly what the cache and the `crt.sh` fallback exist for — do not work around a rate limit by hammering the API harder or by skipping the caching layer "just for now."

## Definition of Done
- [ ] The Tor hidden service is running, its `.onion` address is confirmed reachable, and the Flask app behind it genuinely serves every planted misconfiguration listed in step 2 (verify each one manually with a browser/curl before trusting the automated scanner's output).
- [ ] Running the scanner against the demo target detects every planted misconfiguration and correctly reports what each one leaks (hostname, repo URL, clearnet domain, etc.) — report the actual detector output for each, not just "it works."
- [ ] Running the same detector suite over the ingested historical corpus surfaces at least one real clearnet-domain leak from the actual marketplace data (not the demo target) — report the specific domain and the post it came from.
- [ ] Feed a real clearnet domain (either from the demo target or from the corpus) into the CT pivot and confirm it returns a non-empty set of sibling domains, with the response cached to `data/cache/ct/` and a second run against the same domain reading from cache rather than making a new network call.
- [ ] Confirm the full clearnet-reference → CT-pivot chain (`SPEC.md` §12.1's stated attack chain) works end to end from the demo target: plant → detect → pivot → sibling domain surfaced.
- [ ] Confirm at least one demo-path run wrote `opsec_findings` rows under a real `case_id` (report case_id + finding_kind + value for each).

## Required tests
- `tests/test_ct_pivot.py` — using a cached JSON fixture (no live network call in the test itself), assert the pivot logic extracts the expected sibling-domain set correctly.
- `tests/test_scanner.py` — spin up the demo target (or a test double serving the same planted misconfigurations) and assert every planted misconfiguration is detected by name, not just that the scanner "returns something."
- Extend `tests/test_cases.py` (or add an assertion) so an OpSec write under case A does not appear when listing findings for case B.

## Do not
- Do not scan any hidden service other than the one built in this prompt.
- Do not headline the TLS-certificate detector in any user-facing copy.
- Do not let a live CT API call be required for the scanner or pivot to demonstrate working end to end — the cached path must be sufficient on its own.

## Report back
Report the demo target's confirmed `.onion` reachability, the per-misconfiguration detection results, the real corpus-derived clearnet leak found (with source), the CT pivot output for at least one real domain including confirmation the cache is actually being hit on a repeat call, and both test results.
