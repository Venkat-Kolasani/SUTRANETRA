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

SCRAPE_DATE_RE = re.compile(r"/(\d{4}-\d{2}-\d{2})/")

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
    return "index.php?topic=" in name


def iter_topic_pages(archive_path: Path):
    """Yield (member_path, scrape_date, html) in ascending scrape-date order."""
    with tarfile.open(archive_path, "r:xz") as tar:
        members = [
            m
            for m in tar.getmembers()
            if m.isfile() and is_topic_member(m.name)
        ]
        members.sort(
            key=lambda m: (scrape_date_from_member(m.name) or date.min, m.name)
        )
        for member in members:
            fh = tar.extractfile(member)
            if fh is None:
                continue
            html = fh.read().decode("utf-8", errors="replace")
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
) -> dict:
    archive_path = Path(archive_path)
    source_archive = source_archive or archive_path.name
    init_db(db_path)
    n_pages = 0
    n_parsed = 0
    n_page_failures = 0
    n_skipped_no_date = 0

    # Members come in ascending scrape-date order so INSERT OR REPLACE keeps the newest.
    with sqlite3.connect(db_path) as conn:
        for member_path, scrape_date, html in iter_topic_pages(archive_path):
            if scrape_date is None:
                n_skipped_no_date += 1
                continue
            n_pages += 1
            try:
                page_posts = parse_topic_page(
                    html,
                    market,
                    source_archive=source_archive,
                    scrape_date=scrape_date,
                    source_member_path=member_path,
                )
            except Exception:
                n_page_failures += 1
                continue
            insert_posts(conn, page_posts)
            n_parsed += len(page_posts)
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
        "pages": n_pages,
        "posts_parsed": n_parsed,
        "posts_loaded": n_posts,
        "aliases": n_aliases,
        "page_failures": n_page_failures,
        "skipped_no_date": n_skipped_no_date,
        "null_ts": n_null_ts,
    }


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Ingest a marketplace archive")
    parser.add_argument("--market", default="cannabisroad3")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--archive", default=None, help="Override path to .tar.xz")
    parser.add_argument("--db", default=None)
    args = parser.parse_args(argv)

    with open(args.config, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    raw_dir = cfg["paths"]["data_raw"]
    db_path = args.db or cfg["paths"]["sqlite_db"]

    if args.market != "cannabisroad3" and not args.archive:
        raise SystemExit("Prompt 01 only ships cannabisroad3; pass --archive for others")

    if args.archive:
        archive = Path(args.archive)
        if not archive.is_file():
            raise SystemExit(f"archive not found: {archive}")
    else:
        archive = fetch_archive(raw_dir)

    summary = load_archive(archive, db_path, args.market)
    print(f"archive: {archive}")
    print(f"market:  {args.market}")
    print(f"pages:   {summary['pages']}")
    print(f"posts parsed: {summary['posts_parsed']}")
    print(f"posts loaded: {summary['posts_loaded']}")
    print(f"aliases: {summary['aliases']}")
    print(f"page failures: {summary['page_failures']}")
    print(f"skipped (no scrape date): {summary['skipped_no_date']}")
    print(f"posts with ts=NULL: {summary['null_ts']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
