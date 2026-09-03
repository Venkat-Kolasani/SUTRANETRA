# Prompt 03 — Evidence extraction: PGP, crypto addresses, onion/clearnet, email

## Objective
Pull the deterministic, "hard" identity signals out of every post's raw HTML/body and populate the `evidence` table. This is the strongest evidence class in the whole system — a shared PGP fingerprint or wallet address between two aliases is far stronger proof of common identity than any stylometric similarity score, and the fusion model in Prompt 07 depends on this table being both complete and low-noise.

## Spec references
`SPEC.md` §7 (all subsections), including the verified corpus statistics (23 of 654 sampled `cannabisroad3` thread pages contain a PGP block).

## Preconditions
Prompts 01–02 complete: `posts` populated across the full market set, `raw_html` preserved per post.

## Detailed requirements

### 1. `src/evidence/pgp.py`
- Locate `-----BEGIN PGP PUBLIC KEY BLOCK-----` … `-----END…-----` armored blocks in `raw_html` (unescape HTML entities first — armor markers can be mangled by escaping). Parse with `pgpy` to obtain the key's fingerprint. Store the fingerprint (not the armored blob) as the evidence value — the spec is explicit that fingerprint reuse across aliases is the single strongest link the system produces, so the extractor needs to get this reliably rather than heuristically.
- Also detect and capture `-----BEGIN PGP SIGNED MESSAGE-----` blocks, since signed vendor announcements are common in this corpus and carry a key id even without a full public-key block present.
- Also catch bare fingerprints and key IDs appearing in post signatures outside a formal armor block — a standalone 40-character hexadecimal string, and the same value written as ten space-separated groups of four hex characters, are both valid fingerprint representations in the wild and should be recognized.
- **`pgpy` will fail to parse some 2014-era keys** (old algorithms, malformed armor from scraping artifacts). On a parse failure, do not drop the post's evidence — fall back to extracting the key id or fingerprint directly from the armor header/comment text using a looser pattern match, and record it with a lower-confidence context note. The requirement is "never silently lose a fingerprint because the strict parser choked," not "every fingerprint must come from a successful `pgpy` parse."

### 2. `src/evidence/crypto_addr.py`
- Candidate detection first (regex-shaped scan of the post body for token patterns that look like Bitcoin, Bech32, or Monero addresses), **then mandatory validation before storage**:
  - Bitcoin (legacy/Base58Check): decode the candidate and verify the trailing 4 bytes equal the first 4 bytes of the double-SHA256 hash of the preceding payload bytes. A candidate that fails this check is not evidence — it's noise, and the spec's own research run found real false positives this way (an MD5 hash string and an undersized string both matched a naive regex and are not valid addresses).
  - Bech32 (`bc1…`): validate using the Bech32 checksum algorithm, separately from Base58Check.
  - Monero: match the address-length/prefix shape and apply Monero's own checksum validation.
- Only store candidates that pass validation. This two-stage design (candidate → checksum-validate → store) is not optional simplification territory — it is the difference between an evidence table a judge can trust and one that's full of hash-string noise.

### 3. `src/evidence/onion.py`
- Detect v2 (16-character base32) and v3 (56-character base32) `.onion` hostnames anywhere in the post body.
- Detect clearnet domains referenced in the post body — this matters more than it looks, because these are exactly the references that feed the CT pivot in Prompt 09. The spec's own sample corpus contains a post explicitly tagged `***clearnet***` linking out to a real clearnet domain; extraction should catch both explicitly-tagged and untagged clearnet mentions.
- Detect email addresses, including common obfuscated forms (e.g., a domain written with `[at]`/`[dot]` substitutions) — actors on these forums frequently obfuscate contact info to dodge naive scrapers, and a plain `@`-only regex will systematically miss a meaningful fraction of real addresses.

### 4. `src/evidence/extract.py`
Orchestrates the three extractors above across every post in `posts`, writing rows into `evidence` with `kind` (`pgp_fpr` | `btc` | `xmr` | `onion` | `clearnet` | `email`), `value`, and `context` (roughly ±120 characters of surrounding text, for later display in the report/UI so a human can see the hit in context rather than a bare value).

### 5. Shared-evidence score
Implement the saturating shared-evidence score exactly as specified: pairwise, weight shared PGP fingerprints at 3.0, shared wallets at 2.0, shared onion/clearnet/email at 1.0, sum into `k_weighted`, and compute `S_hard = 1 − 0.5^k_weighted`. Store `n_shared_hard` (the raw evidence-item count, unweighted) alongside the score — the report needs the raw count even though the model only sees the saturating score. This function doesn't need to run over every possible pair yet (that's the blocking step in Prompt 05) — implement and unit-test it as a standalone scoring function first.

## Explicit constraints & known gotchas
- Do not accept a crypto-address candidate on regex match alone, ever. This is the single most important correctness rule in this prompt — see `CLAUDE.md` §5.
- Do not attempt to resolve or contact any extracted onion/clearnet domain from this module. Extraction is passive text-mining over the historical corpus; nothing here makes a network request. (Active CT pivoting on extracted clearnet domains is Prompt 09, and it operates on Certificate Transparency logs, not on the domains directly.)
- The 23-of-654 PGP-block statistic from the spec's own sample is a sanity check, not a hard target — your actual full-corpus PGP hit rate will differ once you're past the single small archive, but it should be the same order of magnitude, not off by 100x in either direction. If it is, investigate before moving on.

## Definition of Done
- [ ] `evidence` is populated across the full corpus with rows for every kind (`pgp_fpr`, `btc`, `onion`, `clearnet`, `email`; `xmr` if any Monero addresses were actually present).
- [ ] Report actual counts per evidence kind across the full corpus.
- [ ] Manually inspect 10 extracted evidence rows per kind (spread across kinds, not all from one kind) against their source post text and confirm they're genuine — not corrupted, not truncated, not a false-positive artifact.
- [ ] Confirm at least one PGP fingerprint and at least one validated wallet address appear on **two or more distinct aliases** somewhere in the corpus — this is the actual signal Prompt 07's fusion model will lean on hardest, so its presence needs to be confirmed now, not assumed.
- [ ] Run the shared-evidence scoring function on a hand-constructed pair (one shared PGP fingerprint, nothing else) and confirm the output is close to the spec's own worked example (~0.88), and on a pair with no shared evidence and confirm the output is exactly 0.

## Required tests
- `tests/test_crypto_addr.py` — the real Bitcoin addresses found in your ingested corpus pass validation; the specific known false positives from the spec (the MD5-hash-shaped string `16936e5adb8a36cbb21d38beeb6f8e11` and the undersized string `3y4kBQhzP5dPh1AiMhNWU7HKLB3`) are correctly rejected. This test *is* the proof of rigor for this module — do not treat it as boilerplate.
- `tests/test_pgp.py` — a known armored PGP block (from your corpus or a fixture) parses to its known, verifiable fingerprint.

## Do not
- Do not skip the checksum-validation stage for any address type "to save time" — an unvalidated crypto-address extractor is worse than none, because it actively damages the evidence table's credibility.
- Do not make any live network request from this module.

## Report back
Report per-kind evidence counts across the full corpus, the results of the 10-per-kind manual spot-checks, confirmation of at least one multi-alias shared PGP/wallet hit found in real data, the shared-evidence-score sanity check output, and both test results.
