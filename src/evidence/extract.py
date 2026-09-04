"""Run PGP / crypto / onion extractors over posts → evidence (SPEC.md §7)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from src.evidence.crypto_addr import extract_crypto
from src.evidence.htmltext import html_to_text
from src.evidence.onion import extract_contacts
from src.evidence.pgp import extract_pgp
from src.ingest.schema import init_db

INSERT_SQL = """
INSERT INTO evidence (alias_id, post_id, kind, value, context)
VALUES (:alias_id, :post_id, :kind, :value, :context)
"""


def extract_from_post(raw_html: str, body: str = "") -> list[dict]:
    # PGP armor lives in raw HTML (entities, <br>). Wallets/contacts are taken
    # from the stripped post body so forum chrome (.onion in the page shell)
    # is not stored as evidence on every row.
    html_text = html_to_text(raw_html)
    body_text = body or html_text
    rows = []
    rows.extend(extract_pgp(html_text))
    rows.extend(extract_crypto(body_text))
    rows.extend(extract_contacts(body_text))
    seen: set[tuple[str, str]] = set()
    uniq = []
    for row in rows:
        key = (row["kind"], row["value"])
        if key in seen:
            continue
        seen.add(key)
        uniq.append(row)
    return uniq


def run(db_path: str | Path, *, replace: bool = True, progress: bool = True) -> dict[str, int]:
    init_db(db_path)
    counts: dict[str, int] = {}
    n_posts = 0
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        if replace:
            conn.execute("DELETE FROM evidence")
        # Stream rows: fetchall() would load every raw_html into RAM (~900k posts).
        cur = conn.execute(
            """
            SELECT p.id AS post_id, p.raw_html, p.body, a.id AS alias_id
            FROM posts p
            LEFT JOIN aliases a ON a.market = p.market AND a.alias = p.alias
            """
        )
        batch = []
        n_fail = 0
        for post in cur:
            n_posts += 1
            try:
                hits = extract_from_post(post["raw_html"], post["body"] or "")
            except Exception:
                n_fail += 1
                continue
            for hit in hits:
                batch.append(
                    {
                        "alias_id": post["alias_id"],
                        "post_id": post["post_id"],
                        "kind": hit["kind"],
                        "value": hit["value"],
                        "context": hit["context"],
                    }
                )
                counts[hit["kind"]] = counts.get(hit["kind"], 0) + 1
                if len(batch) >= 500:
                    conn.executemany(INSERT_SQL, batch)
                    conn.commit()
                    batch.clear()
            if progress and n_posts % 10000 == 0:
                n_ev = sum(v for k, v in counts.items())
                print(f"  scanned {n_posts} posts, {n_ev} evidence so far …", flush=True)
        if batch:
            conn.executemany(INSERT_SQL, batch)
            conn.commit()
    counts["posts_scanned"] = n_posts
    counts["extract_failures"] = n_fail
    counts["evidence_rows"] = sum(
        v for k, v in counts.items() if k not in ("posts_scanned", "evidence_rows")
    )
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
