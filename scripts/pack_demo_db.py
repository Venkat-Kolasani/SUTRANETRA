"""Build a trimmed read-only SQLite for cloud deploy."""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path


def pack(src: Path, dst: Path, case_id: str, max_aliases: int = 80) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        dst.unlink()
    src_uri = src.resolve().as_posix()
    conn = sqlite3.connect(dst)
    conn.execute(f"ATTACH DATABASE '{src_uri}' AS src")
    for table in conn.execute("SELECT sql FROM src.sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"):
        sql = table[0]
        if sql:
            conn.execute(sql)
    conn.execute(
        "INSERT INTO cases SELECT * FROM src.cases WHERE case_id = ?",
        (case_id,),
    )
    alias_ids = [
        r[0]
        for r in conn.execute(
            """
            SELECT alias_id FROM src.clusters WHERE case_id = ?
            UNION
            SELECT a_alias_id FROM src.pair_scores WHERE case_id = ?
            UNION
            SELECT b_alias_id FROM src.pair_scores WHERE case_id = ?
            """,
            (case_id, case_id, case_id),
        )
    ][:max_aliases]
    if not alias_ids:
        conn.commit()
        conn.close()
        return
    qmarks = ",".join("?" * len(alias_ids))
    conn.execute(f"INSERT INTO aliases SELECT * FROM src.aliases WHERE id IN ({qmarks})", alias_ids)
    conn.execute(
        f"INSERT INTO clusters SELECT * FROM src.clusters WHERE case_id = ? AND alias_id IN ({qmarks})",
        [case_id, *alias_ids],
    )
    conn.execute(
        f"""
        INSERT INTO pair_scores SELECT * FROM src.pair_scores
        WHERE case_id = ? AND a_alias_id IN ({qmarks}) AND b_alias_id IN ({qmarks})
        """,
        [case_id, *alias_ids, *alias_ids],
    )
    conn.execute(
        f"INSERT INTO evidence SELECT * FROM src.evidence WHERE alias_id IN ({qmarks})",
        alias_ids,
    )
    post_ids = [r[0] for r in conn.execute("SELECT DISTINCT post_id FROM evidence WHERE post_id IS NOT NULL")]
    if post_ids:
        pq = ",".join("?" * len(post_ids))
        conn.execute(f"INSERT OR IGNORE INTO posts SELECT * FROM src.posts WHERE id IN ({pq})", post_ids)
    conn.execute("INSERT INTO opsec_findings SELECT * FROM src.opsec_findings WHERE case_id = ?", (case_id,))
    conn.commit()
    conn.close()


def main() -> None:
    p = argparse.ArgumentParser(description="Pack a cloud demo SQLite snapshot")
    p.add_argument("--src", default="data/db/attrib.sqlite")
    p.add_argument("--dst", default="data/demo/attrib.sqlite")
    p.add_argument("--case-id", default="CASE-2026-001")
    p.add_argument("--max-aliases", type=int, default=80)
    args = p.parse_args()
    pack(Path(args.src), Path(args.dst), args.case_id, args.max_aliases)
    print("wrote", args.dst, "bytes", Path(args.dst).stat().st_size)


if __name__ == "__main__":
    main()
