"""Blocking force-includes hard-evidence pairs outside the FAISS top-k."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from src.ingest.schema import init_db
from src.stylometry.blocking import (
    hard_evidence_pairs,
    neighbor_pairs,
    reduce_for_index,
    union_candidates,
)
from src.stylometry.char_ngram import fit_char_tfidf


def _seed(db: Path) -> None:
    init_db(db)
    conn = sqlite3.connect(db)
    # Two style clusters of 51 aliases each. A pair across clusters that
    # shares PGP will not appear in either side's top-50 neighbours.
    rows = []
    posts = []
    msg = 1
    for cluster, base in (("aaa well shipping asap!! ", "x"), ("zzz qqq xkcd prose ", "y")):
        for i in range(51):
            alias_id = msg
            alias = f"{base}{i}"
            market = "silkroad1" if base == "x" else "agora"
            rows.append((alias_id, market, alias, 5))
            body = (cluster * 12) + f" uniq{base}{i} "
            posts.append(
                (
                    market,
                    msg,
                    alias,
                    body,
                    f"<div class='inner'>{body}</div>",
                    "a.tar.xz",
                    "2014-01-01",
                    f"m{msg}",
                    f"h{msg}",
                )
            )
            msg += 1
    conn.executemany(
        "INSERT INTO aliases (id, market, alias, n_posts) VALUES (?,?,?,?)",
        rows,
    )
    conn.executemany(
        """
        INSERT INTO posts (
          market, msg_id, alias, body, raw_html,
          source_archive, scrape_date, source_member_path, content_sha256
        ) VALUES (?,?,?,?,?,?,?,?,?)
        """,
        posts,
    )
    # x0 is id 1; y0 is id 52
    conn.execute(
        "INSERT INTO evidence (alias_id, post_id, kind, value) VALUES (1, 1, 'pgp_fpr', 'DEADBEEF')"
    )
    conn.execute(
        "INSERT INTO evidence (alias_id, post_id, kind, value) VALUES (52, 52, 'pgp_fpr', 'DEADBEEF')"
    )
    conn.commit()
    conn.close()


def test_hard_evidence_pair_force_included_outside_top50(tmp_path: Path):
    db = tmp_path / "b.sqlite"
    _seed(db)
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    alias_ids = [r[0] for r in conn.execute("SELECT id FROM aliases ORDER BY id")]
    docs = [
        r[0]
        for r in conn.execute(
            """
            SELECT p.body FROM aliases a
            JOIN posts p ON p.market = a.market AND p.alias = a.alias
            ORDER BY a.id
            """
        )
    ]
    _vec, x = fit_char_tfidf(docs, min_df=1, max_features=5000)
    dense = reduce_for_index(x, n_components=32)
    neighbors = neighbor_pairs(dense, alias_ids, top_k=50)
    hard = hard_evidence_pairs(conn)
    pair = (1, 52)
    assert pair in hard
    assert pair not in neighbors
    candidates = union_candidates(neighbors, hard, set())
    assert pair in candidates
    conn.close()
