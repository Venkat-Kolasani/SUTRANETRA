"""Fetch → stream-parse → dedupe-load posts/aliases (SPEC.md §5–§6.1)."""

from __future__ import annotations

import re
import sqlite3
import tarfile
from datetime import date
from pathlib import Path

import yaml

from src.ingest.fetch import fetch_archive
from src.ingest.schema import init_db
from src.ingest.smf_parser import Post, parse_topic_page

# Lazy import for phpBB parser — only loaded if a market's HTML doesn't match SMF.
_phpbb_parser = None


def _get_phpbb_parser():
    global _phpbb_parser
    if _phpbb_parser is None:
        from src.ingest import phpbb_parser as _mod
        _phpbb_parser = _mod
    return _phpbb_parser


SCRAPE_DATE_RE = re.compile(r"/(\d{4}-\d{2}-\d{2})/")
TOPIC_MEMBER_RE = re.compile(r"(index\.php\?topic=|viewtopic\.php)")

INSERT_POST_SQL = """
INSERT OR REPLACE INTO posts (
  market, msg_id, alias, user_id, thread_id, subject, ts, body, raw_html,
  membergroup, postcount, karma_pos, karma_neg, onion_host,
  source_archive, scrape_date, source_member_path, content_sha256
) VALUES (
  :market, :msg_id, :alias, :user_id, :thread_id, :subject, :ts, :body, :raw_html,
  :membergroup, :postcount, :karma_pos, :karma_neg, :onion_host,
  :source_archive, :scrape_date, :source_member_path, :content_sha256
)
"""
# INSERT OR REPLACE (not IGNORE): UNIQUE(market, msg_id) must keep the newest
# scrape. IGNORE would silently keep the oldest copy and stale lineage.

UPSERT_ALIAS_SQL = """
INSERT INTO aliases (market, alias, n_posts, first_seen, last_seen, is_vendor)
VALUES (:market, :alias, :n_posts, :first_seen, :last_seen, :is_vendor)
ON CONFLICT(market, alias) DO UPDATE SET
  n_posts = excluded.n_posts,
  first_seen = excluded.first_seen,
  last_seen = excluded.last_seen,
  is_vendor = excluded.is_vendor
"""


def scrape_date_from_member(name: str) -> date | None:
    m = SCRAPE_DATE_RE.search("/" + name.replace("\\", "/") + "/")
    return date.fromisoformat(m.group(1)) if m else None


def is_topic_member(name: str) -> bool:
    return bool(TOPIC_MEMBER_RE.search(name))


def _topic_members(tar: tarfile.TarFile):
    members = [
        m for m in tar.getmembers() if m.isfile() and is_topic_member(m.name)
    ]
    members.sort(key=lambda m: (scrape_date_from_member(m.name) or date.min, m.name))
    return members


def _read_member(tar: tarfile.TarFile, member: tarfile.TarInfo) -> str | None:
    fh = tar.extractfile(member)
    if fh is None:
        return None
    return fh.read().decode("utf-8", errors="replace")


def detect_forum_type_from_html(html: str) -> str | None:
    if "div.post_wrapper" in html or 'class="post_wrapper"' in html:
        return "smf"
    if (
        "div.postbody" in html
        or 'class="postbody"' in html
        or 'id="punviewtopic"' in html
    ):
        return "phpbb"
    return None


def detect_forum_type(archive_path: Path) -> str:
    """Sample a few topic pages to detect SMF vs phpBB markup."""
    with tarfile.open(archive_path, "r:xz") as tar:
        seen = 0
        for member in tar.getmembers():
            if not member.isfile() or not is_topic_member(member.name):
                continue
            html = _read_member(tar, member)
            if html is None:
                continue
            kind = detect_forum_type_from_html(html)
            if kind:
                return kind
            seen += 1
            if seen >= 5:
                break
    return "unknown"


def iter_topic_pages(archive_path: Path):
    """Yield (member_path, scrape_date, html) in ascending scrape-date order."""
    with tarfile.open(archive_path, "r:xz") as tar:
        for member in _topic_members(tar):
            html = _read_member(tar, member)
            if html is None:
                continue
            yield member.name, scrape_date_from_member(member.name), html


def post_to_row(post: Post) -> dict:
    return {
        "market": post.market,
        "msg_id": post.msg_id,
        "alias": post.alias,
        "user_id": post.user_id,
        "thread_id": post.thread_id,
        "subject": post.subject,
        "ts": post.ts.isoformat(sep=" ") if post.ts else None,
        "body": post.body,
        "raw_html": post.raw_html,
        "membergroup": post.membergroup,
        "postcount": post.postcount,
        "karma_pos": post.karma_pos,
        "karma_neg": post.karma_neg,
        "onion_host": post.onion_host,
        "source_archive": post.source_archive,
        "scrape_date": post.scrape_date.isoformat(),
        "source_member_path": post.source_member_path,
        "content_sha256": post.content_sha256,
    }


def insert_posts(conn: sqlite3.Connection, posts: list[Post]) -> int:
    conn.executemany(INSERT_POST_SQL, [post_to_row(p) for p in posts])
    return len(posts)


def refresh_aliases(conn: sqlite3.Connection, market: str) -> int:
    # is_vendor: heuristic only — membergroup containing "vendor" (any case).
    # Sample value: "Cannabis Road Legacy Vendor"; not a guarantee of vendor status.
    rows = conn.execute(
        """
        SELECT alias,
               COUNT(*) AS n_posts,
               MIN(ts) AS first_seen,
               MAX(ts) AS last_seen,
               MAX(CASE WHEN membergroup IS NOT NULL
                         AND LOWER(membergroup) LIKE '%vendor%'
                        THEN 1 ELSE 0 END) AS is_vendor
        FROM posts
        WHERE market = ?
        GROUP BY alias
        """,
        (market,),
    ).fetchall()
    payload = [
        {
            "market": market,
            "alias": r[0],
            "n_posts": r[1],
            "first_seen": r[2],
            "last_seen": r[3],
            "is_vendor": r[4],
        }
        for r in rows
    ]
    conn.executemany(UPSERT_ALIAS_SQL, payload)
    return len(payload)


def load_archive(
    archive_path: str | Path,
    db_path: str | Path,
    market: str,
    source_archive: str | None = None,
    forum_type: str | None = None,
    progress: bool = True,
) -> dict:
    archive_path = Path(archive_path)
    source_archive = source_archive or archive_path.name
    init_db(db_path)

    n_pages = 0
    n_parsed = 0
    n_page_failures = 0
    n_skipped_no_date = 0
    batch: list[Post] = []
    BATCH_SIZE = 500
    _parse = None

    # One tar open: list once, detect from the first topic pages, then parse.
    # Members are processed in ascending scrape-date order so INSERT OR REPLACE
    # keeps the newest scrape.
    with tarfile.open(archive_path, "r:xz") as tar, sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        members = _topic_members(tar)
        for member in members:
            scrape_date = scrape_date_from_member(member.name)
            if scrape_date is None:
                n_skipped_no_date += 1
                continue
            html = _read_member(tar, member)
            if html is None:
                continue
            if _parse is None:
                detected = forum_type or detect_forum_type_from_html(html)
                if detected == "phpbb":
                    _parse = _get_phpbb_parser().parse_topic_page
                    forum_type = "phpbb"
                elif detected == "smf":
                    _parse = parse_topic_page
                    forum_type = "smf"
                else:
                    continue
            n_pages += 1
            try:
                page_posts = _parse(
                    html,
                    market,
                    source_archive=source_archive,
                    scrape_date=scrape_date,
                    source_member_path=member.name,
                )
            except Exception:
                n_page_failures += 1
                continue
            batch.extend(page_posts)
            n_parsed += len(page_posts)
            if len(batch) >= BATCH_SIZE:
                insert_posts(conn, batch)
                conn.commit()
                batch.clear()
            if progress and n_pages % 2000 == 0:
                print(
                    f"  [{market}] {n_pages} pages, {n_parsed} posts so far …",
                    flush=True,
                )
        if _parse is None:
            raise ValueError(f"unknown forum type for {market}: {forum_type or 'unknown'}")
        if batch:
            insert_posts(conn, batch)
            conn.commit()
            batch.clear()
        n_aliases = refresh_aliases(conn, market)
        n_posts = conn.execute(
            "SELECT COUNT(*) FROM posts WHERE market = ?", (market,)
        ).fetchone()[0]
        n_null_ts = conn.execute(
            "SELECT COUNT(*) FROM posts WHERE market = ? AND ts IS NULL",
            (market,),
        ).fetchone()[0]
        conn.commit()

    return {
        "forum_type": forum_type,
        "pages": n_pages,
        "posts_parsed": n_parsed,
        "posts_loaded": n_posts,
        "aliases": n_aliases,
        "page_failures": n_page_failures,
        "skipped_no_date": n_skipped_no_date,
        "null_ts": n_null_ts,
    }


def run(
    db_path: str | Path,
    cfg: dict,
    *,
    markets: list[str] | None = None,
) -> dict:
    """Load archives that exist on disk; skip markets already in SQLite."""
    init_db(db_path)
    markets = list(markets if markets is not None else cfg.get("markets") or [])
    raw_dir = Path((cfg.get("paths") or {}).get("data_raw") or "data/raw")
    loaded: dict[str, dict] = {}
    with sqlite3.connect(db_path) as conn:
        for market in markets:
            n = conn.execute(
                "SELECT COUNT(*) FROM posts WHERE market = ?", (market,)
            ).fetchone()[0]
            if n > 0:
                loaded[market] = {"skipped": "already_loaded", "posts_loaded": n}
                continue
            archive = raw_dir / f"{market}-forums.tar.xz"
            if not archive.is_file():
                loaded[market] = {"skipped": "no_archive"}
                continue
            loaded[market] = load_archive(archive, db_path, market, progress=False)
    with sqlite3.connect(db_path) as conn:
        n_posts = conn.execute("SELECT COUNT(*) FROM posts").fetchone()[0]
        n_aliases = conn.execute("SELECT COUNT(*) FROM aliases").fetchone()[0]
    return {"n_posts": n_posts, "n_aliases": n_aliases, "markets": loaded}


def _print_summary(market: str, archive: Path, summary: dict) -> None:
    print(f"\n{'=' * 60}", flush=True)
    print(f"market:  {market}", flush=True)
    print(f"archive: {archive}", flush=True)
    print(f"parser:  {summary.get('forum_type', '?')}", flush=True)
    print(f"pages:   {summary['pages']}", flush=True)
    print(f"posts parsed: {summary['posts_parsed']}", flush=True)
    print(f"posts loaded: {summary['posts_loaded']}", flush=True)
    print(f"aliases: {summary['aliases']}", flush=True)
    print(f"page failures: {summary['page_failures']}", flush=True)
    print(f"skipped (no scrape date): {summary['skipped_no_date']}", flush=True)
    print(f"posts with ts=NULL: {summary['null_ts']}", flush=True)


def main(argv: list[str] | None = None) -> int:
    import argparse
    import time

    parser = argparse.ArgumentParser(description="Ingest marketplace archives")
    parser.add_argument(
        "--market",
        default=None,
        help="Single market name, or 'all' for every market in config",
    )
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--archive", default=None, help="Override path to .tar.xz")
    parser.add_argument("--db", default=None)
    args = parser.parse_args(argv)

    with open(args.config, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    raw_dir = cfg["paths"]["data_raw"]
    db_path = args.db or cfg["paths"]["sqlite_db"]
    all_markets: list[str] = cfg.get("markets", [])

    if args.market and args.market != "all":
        markets = [args.market]
    elif args.market == "all":
        markets = all_markets
    else:
        markets = ["cannabisroad3"]

    skipped: list[tuple[str, str]] = []
    results: dict[str, dict] = {}

    for market in markets:
        print(f"\n>>> {market}", flush=True)

        # Fetch
        if args.archive and len(markets) == 1:
            archive = Path(args.archive)
            if not archive.is_file():
                raise SystemExit(f"archive not found: {archive}")
        else:
            try:
                print(f"  fetching {market} …", flush=True)
                t0 = time.time()
                archive = fetch_archive(raw_dir, market)
                print(f"  fetched in {time.time() - t0:.1f}s", flush=True)
            except Exception as exc:
                reason = f"fetch failed: {exc}"
                print(f"  SKIP {market}: {reason}", flush=True)
                skipped.append((market, reason))
                continue

        # Ingest
        try:
            t0 = time.time()
            summary = load_archive(archive, db_path, market)
            elapsed = time.time() - t0
            _print_summary(market, archive, summary)
            print(f"  elapsed: {elapsed:.1f}s", flush=True)
            results[market] = summary
        except Exception as exc:
            reason = f"ingest failed: {exc}"
            print(f"  SKIP {market}: {reason}", flush=True)
            skipped.append((market, reason))

    # Grand totals
    import sqlite3 as _s

    conn = _s.connect(db_path)
    total_posts = conn.execute("SELECT COUNT(*) FROM posts").fetchone()[0]
    total_aliases = conn.execute("SELECT COUNT(*) FROM aliases").fetchone()[0]
    market_list = [
        r[0] for r in conn.execute("SELECT DISTINCT market FROM posts").fetchall()
    ]
    null_lineage = conn.execute(
        "SELECT COUNT(*) FROM posts WHERE source_archive IS NULL "
        "OR scrape_date IS NULL OR source_member_path IS NULL "
        "OR content_sha256 IS NULL OR raw_html IS NULL"
    ).fetchone()[0]
    conn.close()

    print(f"\n{'=' * 60}", flush=True)
    print("GRAND TOTALS", flush=True)
    print(f"  total posts:   {total_posts}", flush=True)
    print(f"  total aliases: {total_aliases}", flush=True)
    print(f"  markets:       {market_list}", flush=True)
    print(f"  null lineage:  {null_lineage}", flush=True)
    if skipped:
        print("SKIPPED:", flush=True)
        for m, r in skipped:
            print(f"  {m}: {r}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
