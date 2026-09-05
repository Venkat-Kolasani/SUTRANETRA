# Ethics statement — SUTRANETRA

This statement records how SUTRANETRA was built and what its outputs mean. It is an operating constraint, not marketing copy.

## 1. No live criminal infrastructure

We do not scrape Tor, do not log into any marketplace, and do not interact with any third-party hidden service at any point in this build — including “just to check.” All forum text comes from offline archives already on disk.

## 2. Historical, public corpus

The Darknet Market Archives hosted on archive.org are the source corpus. The markets involved shut down years ago (roughly 2013–2015 for the five we ingest). The same archives are the standard dataset in peer-reviewed cybercrime research. We treat them as a historical research corpus, not as a live investigative feed.

## 3. Only our own hidden service is scanned

The OpSec leak scanner’s only Tor target is a hidden service this team creates on localhost, deliberately misconfigured for the demo. `src/opsec/scanner.py` rejects non-localhost targets. We do not scan anyone else’s onion.

## 4. Certificate Transparency is public by design

CT-log pivots use public Certificate Transparency data (cache-first under `data/cache/`; live queries are opt-in). CT exists so issued certificates can be audited. Querying it does not require accessing a hidden service.

## 5. Intended use

SUTRANETRA is built for the SIH26151 / NTRO law-enforcement attribution use case: help investigators correlate pseudonymous marketplace aliases and surface infrastructure leaks that justify further lawful investigation. It is not a consumer de-anonymization product.

## 6. Pseudonyms with confidence, never verdicts

Wallets, PGP fingerprints, and handles extracted from the corpus are stored and shown as **pseudonymous identifiers** with a correlation confidence score. UI copy, template explanations, and PDF exports state that SUTRANETRA reports evidence and confidence — not an identity claim and not a guilty verdict. Same-handle cross-market labels used for training are themselves a heuristic (handle squatting exists); we say so in evaluation notes.
