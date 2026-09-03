# Prompt 01 — Ingest bootstrap: fetch + SMF parser on `cannabisroad3`

## Objective
Get one small archive (`cannabisroad3-forums.tar.xz`, 2.2 MB) flowing end-to-end: download → stream-parse → dedupe → write into the `posts`/`aliases` tables built in Prompt 00, **with immutable source lineage on every post**. This is the step that proves the entire ingest approach works before you scale it to archives that are 100–500x larger. Everything here is built to be deliberately small and fast to iterate on.

## Spec references
`SPEC.md` §5 (data acquisition, verified archive structure), §6 (SMF parser, selector map, schema, dedupe rule), §6.1 (source lineage).

## Preconditions
Prompt 00 complete: schema exists and verified (including lineage columns + `raw_html`), `config.yaml` parses, core dependencies installed.

## Detailed requirements

### 1. `src/ingest/fetch.py`
Download `https://archive.org/download/dnmarchives/cannabisroad3-forums.tar.xz` into `data/raw/`, skip the download if the file already exists locally (idempotent, since re-downloading a corpus repeatedly during development wastes time and bandwidth), and verify the download completed (non-zero size, and ideally that it's a valid xz-compressed tar rather than a truncated file or an HTML error page saved with the wrong extension — archive.org occasionally serves an error page instead of the file on a bad request, and that failure mode is silent unless you check).

### 2. `src/ingest/smf_parser.py`
Implement the `Post` structure and `parse_topic_page` function described in `SPEC.md` §6, reading directly from the tar stream — **never write extracted files to disk**, use `tarfile.extractfile(member).read()` for every member you touch. The parser must:
- Accept `source_archive`, `scrape_date`, and `source_member_path` from the loader (derived from the `.tar.xz` filename, the scrape-date directory, and the tar member name) and set them on every `Post`.
- Compute `content_sha256 = sha256(raw_html.encode("utf-8")).hexdigest()` for each post block.
- Only process members whose path contains `index.php?topic=` (thread pages) — skip everything else (avatars, theme assets, profile pages at this stage).
- Extract one `Post` per `div.post_wrapper` block on the page, pulling: alias from `div.poster h4 a`, `user_id` from the profile-link `href` (`action=profile;u=(\d+)`), `membergroup` from `li.membergroup`, post/karma counts from `li.postcount` / `li.karma`, subject from `div.keyinfo h5 a`, timestamp from `div.keyinfo div.smalltext` after stripping the `« on: … »` wrapper, `msg_id` from the post container's `id="msg_NNNN"` attribute, and body text from `div.post div.inner` with `<br />` converted to newlines and HTML entities unescaped. Keep `raw_html` for the post block intact and unmodified — later evidence extraction (Prompt 03) needs PGP blocks that plain-text extraction would mangle.
- Parse timestamps using the format `%B %d, %Y, %I:%M:%S %p`. Handle SMF's relative form ("Today at …") by resolving it against the scrape date encoded in the containing directory name. If a timestamp genuinely can't be parsed, set `ts = None` — do not guess, and do not drop the post; it simply won't participate in the temporal feature later.
- Decode all HTML with `errors='replace'` — these are 2014-era scrapes and some are mojibake. The parser must not crash on malformed encoding; it should produce best-effort text and keep going.
- Extract any absolute `.onion` URL appearing in the post (16-character v2 or 56-character v3 form, base32 alphabet) into the `onion_host` field — this is the forum's own onion address as referenced within its own pages, not evidence extraction proper (that's Prompt 03's job for onion references to *other* services).

### 3. `src/ingest/load.py`
Read parsed posts and write them into `posts` using `INSERT OR REPLACE` keyed on `(market, msg_id)`, **processing scrape dates in ascending order** so that the newest scrape always wins the replace — and the winning row must carry **that scrape's** lineage fields (`source_archive`, `scrape_date`, `source_member_path`, `content_sha256`) together with the body/`raw_html`. Explain in a code comment why `INSERT OR REPLACE` was chosen over `INSERT OR IGNORE` — this is a correctness-critical decision (`AGENTS.md` / `CLAUDE.md` §5) and future maintainers should not "simplify" it. After loading `posts`, populate/refresh the `aliases` table: one row per distinct `(market, alias)`, with `n_posts`, `first_seen`, `last_seen` derived from the posts just loaded, and `is_vendor` set from whether any of that alias's `membergroup` values indicate vendor status (the spec's sample shows `"Cannabis Road Legacy Vendor"` as one such value — treat membergroup text containing "vendor" case-insensitively as the initial heuristic, and note it as a heuristic, not a guarantee, in a comment).

### 4. CLI entry point
`python -m src.ingest.load --market cannabisroad3` (or equivalent) should run fetch → parse → dedupe-load as one command, printing a summary (posts loaded, aliases created, any parse failures) at the end.

## Explicit constraints & known gotchas
- The same 2.2 MB archive contains **four separate scrape dates that re-scrape the same threads**. If dedupe is wrong, every post gets counted up to 4×. The spec states ~10,914 members but only ~10,490 non-asset — use this as a sanity range, not an exact assertion, since your own count depends on exactly how you filter.
- `pgpy` and evidence extraction are **not** part of this prompt — `raw_html` just needs to be preserved correctly for Prompt 03 to use later. Do not attempt PGP parsing here.
- Do not build the phpBB fallback parser in this prompt. `cannabisroad3` is confirmed SMF. Build `phpbb_parser.py` only when Prompt 02 hits a market that actually fails the SMF selectors — building it speculatively now means maintaining code with nothing to test it against.
- Lineage is written at ingest time only — never backfill with guesses later.

## Definition of Done
- [ ] `cannabisroad3-forums.tar.xz` downloads successfully and re-running the fetch step does not re-download it.
- [ ] Running the ingest CLI end-to-end populates the `posts` table with a plausible number of rows (in the low thousands, not tens of thousands and not near-zero — sanity-check the actual count against what you'd expect from a 2.2 MB archive of forum HTML).
- [ ] Manually pull 5 arbitrary posts from the database and compare each field (alias, timestamp, msg_id, body) against the actual HTML by eye — open the source page from the tar and check it by hand. This is the spec's own acceptance bar for this step (`SPEC.md` §17, row 1) — do not skip it just because the automated tests pass.
- [ ] Confirm no thread appears duplicated: pick a `msg_id` that you can see occurs across multiple scrape-date folders in the raw archive, and confirm it exists exactly once in `posts`, with the field values **and lineage** from the *newest* scrape date, not an older one.
- [ ] Every inspected post has non-null `source_archive`, `scrape_date`, `source_member_path`, `content_sha256`, and `raw_html`; recomputing sha256 from stored `raw_html` matches `content_sha256`.
- [ ] The `aliases` table is populated with one row per distinct `(market, alias)` pair, `n_posts`/`first_seen`/`last_seen` are correct for at least the 5 aliases you spot-checked, and at least one alias is correctly flagged `is_vendor = 1`.
- [ ] Posts with unparseable timestamps have `ts = NULL` in the database (not a fabricated value) and are still present in `posts`.

## Required tests
- `tests/test_smf_parser.py` — save one real thread-page HTML fixture from the downloaded archive into `tests/fixtures/`, and assert the parser extracts the exact expected alias, timestamp, `msg_id`, and body text for every post on that page. This is a golden-file test: the fixture must be real HTML you've inspected by hand, not synthetic HTML you wrote yourself, or the test proves nothing about the actual selectors.
- `tests/test_dedupe.py` — construct (or reuse) a fixture where the same thread appears across at least 2 of the archive's scrape-date folders, run the load step, and assert the final post count for that thread is unchanged by the duplication **and** that the surviving row's `scrape_date` / `source_member_path` / `content_sha256` match the newest scrape.
- `tests/test_post_provenance.py` — assert lineage columns are non-null on loaded fixture posts; recomputed sha256 matches; a synthetic evidence→post join returns archive/scrape/member/hash fields (even if evidence rows are inserted only for the test).

## Do not
- Do not extract the archive to disk anywhere, including "temporarily for debugging." Stream reads only.
- Do not write the phpBB parser, evidence extraction, or anything beyond `cannabisroad3` in this prompt.

## Report back
Report the actual row counts for `posts` and `aliases` after ingesting `cannabisroad3`, the results of the 5-post manual spot-check (quote at least one full comparison including lineage), the dedupe verification result, and all three test outcomes. Update `docs/build-log.md`.
