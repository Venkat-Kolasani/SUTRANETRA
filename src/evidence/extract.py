"""Run PGP / crypto / onion extractors over posts → evidence (SPEC.md §7)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from src.evidence.crypto_addr import extract_crypto_from_html
from src.evidence.onion import extract_contacts_from_html
from src.evidence.pgp import extract_pgp_from_html
from src.ingest.schema import init_db

INSERT_SQL = """
INSERT INTO evidence (alias_id, post_id, kind, value, context)
VALUES (:alias_id, :post_id, :kind, :value, :context)
"""


def extract_from_post(raw_html: str, body: str = "") -> list[dict]:
    rows = []
    rows.extend(extract_pgp_from_html(raw_html, body))
    rows.extend(extract_crypto_from_html(raw_html, body))
    rows.extend(extract_contacts_from_html(raw_html, body))
    # De-dupe identical hits from overlapping extractors.
    seen: set[tuple[str, str]] = set()
    uniq = []
    for row in rows:
        key = (row["kind"], row["value"])
        if key in seen:
            continue
        seen.add(key)
        uniq.append(row)
    return uniq


def run(db_path: str | Path, *, replace: bool = True) -> dict[str, int]:
    init_db(db_path)
    counts: dict[str, int] = {}
    n_posts = 0
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        if replace:
            conn.execute("DELETE FROM evidence")
        posts = conn.execute(
            """
            SELECT p.id AS post_id, p.raw_html, p.body, a.id AS alias_id
            FROM posts p
            LEFT JOIN aliases a ON a.market = p.market AND a.alias = p.alias
            """
        ).fetchall()
        batch = []
        for post in posts:
            n_posts += 1
            for hit in extract_from_post(post["raw_html"], post["body"] or ""):
                hit = {
                    "alias_id": post["alias_id"],
                    "post_id": post["post_id"],
                    "kind": hit["kind"],
                    "value": hit["value"],
                    "context": hit["context"],
                }
                batch.append(hit)
                counts[hit["kind"]] = counts.get(hit["kind"], 0) + 1
                if len(batch) >= 500:
                    conn.executemany(INSERT_SQL, batch)
                    conn.commit()
                    batch.clear()
        if batch:
            conn.executemany(INSERT_SQL, batch)
            conn.commit()
    counts["posts_scanned"] = n_posts
    counts["evidence_rows"] = sum(v for k, v in counts.items() if k != "posts_scanned")
    return counts


def main(argv: list[str] | None = None) -> int:
    import argparse

    import yaml

    parser = argparse.ArgumentParser(description="Extract hard evidence from posts")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--db", default=None)
    args = parser.parse_args(argv)
    with open(args.config, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    db_path = args.db or cfg["paths"]["sqlite_db"]
    counts = run(db_path)
    print("evidence extraction")
    for k in sorted(counts):
        print(f"  {k}: {counts[k]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
