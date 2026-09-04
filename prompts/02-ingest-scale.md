# Prompt 02 — Scale ingestion to the full market set

## Objective
Take the proven `cannabisroad3` pipeline from Prompt 01 and run it across the full recommended market set, so the corpus is large enough and spans enough overlapping timeframes for cross-market attribution to be meaningful later. This is where the phpBB fallback parser gets built — but only if and when it's actually needed.

## Spec references
`SPEC.md` §5 (market list, sizes, rationale), §6 (phpBB fallback note), §6.1 (lineage must remain non-null at scale).

## Preconditions
Prompt 01 complete and verified: `cannabisroad3` ingests cleanly, dedupe is correct, lineage fields verified, the 5-post spot-check passed.

## Detailed requirements

### 1. Ingest order
Follow the spec's own recommended sequence, smallest-and-safest first: `nucleus-forums.tar.xz` (134 MB) next as a fast dev-loop check that the pipeline holds up on something an order of magnitude bigger than `cannabisroad3`, then the larger four — `silkroad1-forums.tar.xz`, `silkroad2-forums.tar.xz`, `agora-forums.tar.xz`, `evolution-forums.tar.xz` — and `thehub-forums.tar.xz` (the cross-market meta-forum, valuable specifically because vendors from every market post there, which is a source of extra cross-market signal beyond same-username matching alone).

### 2. Per-market dispatch and the phpBB fallback
Before parsing a market with the SMF parser, detect whether the market's HTML actually matches SMF markup (presence of `div.post_wrapper` on a sample page). If a market does **not** match, that is the trigger — and the only trigger — to write `src/ingest/phpbb_parser.py`, targeting the phpBB markup shape (`div.postbody`, `p.author`, and whatever else the actual failing market's HTML requires — inspect it directly rather than assuming a shape). If every market in this prompt's list happens to parse fine under SMF, do not write the phpBB parser at all — the spec is explicit that it should not be built speculatively.

### 3. Resilience over completeness
If a specific market's archive is corrupt, absent, or its layout doesn't match either parser after a reasonable investigation, **skip that market and continue** rather than blocking the whole ingest run. Log which markets were skipped and why. Five working markets is enough for the project to succeed; stalling the whole pipeline on one bad archive is not an acceptable trade.

### 4. Streaming and disk discipline still apply
Agora is roughly 869 MB compressed and 8–10 GB uncompressed. The streaming approach from Prompt 01 is not optional at this scale — it is the only thing standing between this step and filling a laptop's disk. Re-confirm nothing is being extracted to disk before running the largest archives.

### 5. Progress and resumability
An ingest run across all six-plus archives will take on the order of tens of minutes. Provide visible progress output (which market, how many posts so far) so a stalled run is distinguishable from a slow one, and make each market's ingest independently re-runnable (re-running `nucleus` after `agora` already succeeded should not require re-ingesting `agora`).

## Explicit constraints & known gotchas
- Don't build in a general-purpose "detect any forum software" abstraction. Two parsers (SMF, phpBB-if-needed) covering the specific markets in this list is the actual requirement — a speculative plugin architecture for hypothetical future forum software is scope creep this project doesn't need.
- The final corpus size target from the spec's own build-order table (`SPEC.md` §17, row 2) is **at least 1 million posts across at least 5 markets**. Treat that as the acceptance bar, not a guess — if you're well short after ingesting the full list, investigate before moving on rather than declaring the step done with a much smaller corpus.
- If `thehub` turns out to have a genuinely different structure from the others, it's still worth the ingest effort even if it needs its own small adjustment — it's called out in the spec specifically because of its cross-market signal value, and losing it weakens Prompt 04's label set.

## Definition of Done
- [ ] `posts` contains at least 1,000,000 rows spanning at least 5 distinct markets (query and report the actual count and the actual market list — do not estimate).
- [ ] `SELECT COUNT(*) FROM posts WHERE source_archive IS NULL OR scrape_date IS NULL OR source_member_path IS NULL OR content_sha256 IS NULL OR raw_html IS NULL` returns **0**.
- [ ] For each market ingested, report: raw post count, alias count, date range covered, whether SMF or phpBB parsing was used, and a sample lineage triple (archive / scrape_date / member path).
- [ ] Any skipped market is explicitly listed with a one-line reason (corrupt archive, layout mismatch investigated and deemed not worth a custom parser, etc.) — "silently missing" is not an acceptable end state; "explicitly skipped and here's why" is.
- [ ] Re-running the ingest command for a market that already succeeded does not create duplicate rows and does not re-download the archive.
- [ ] If the phpBB parser was written, it passes its own spot-check against 5 real posts from the market that triggered it, the same way Prompt 01 required for SMF, **including lineage fields**.

## Required tests
- Extend `tests/test_smf_parser.py` (or add a market-specific fixture case) to cover at least one additional market beyond `cannabisroad3`, confirming the selectors generalize rather than having been accidentally overfit to one archive's specific quirks.
- If `phpbb_parser.py` was written: `tests/test_phpbb_parser.py`, structured the same way as the SMF golden-file test — a real saved fixture, exact field assertions, lineage populated.
- Re-run `tests/test_dedupe.py` and `tests/test_post_provenance.py` against at least one multi-market load path and confirm totals stay stable across two consecutive ingest runs of the same market list.

## Do not
- Do not write a generic multi-forum-software abstraction layer "for future-proofing." Two concrete parsers, built only as needed, is correct scope.
- Do not silently drop a market from the corpus without logging why.

## Report back
Report the final total row counts for `posts` and `aliases`, the per-market breakdown, the list of any skipped markets with reasons, and confirm the ≥1M-post / ≥5-market bar from the spec's build order was actually met (or explain precisely how far short and why, if it wasn't).
