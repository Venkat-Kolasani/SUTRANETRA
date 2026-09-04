"""Label-set generator: same-username positives; hard negs have no shared evidence."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from src.fusion.labels import generate_labels
from src.ingest.schema import init_db

KNOWN_CORPUS_ALIAS = "Jack N Hoff"
KNOWN_MARKETS = ("silkroad1", "silkroad2")


def _seed(db: Path) -> sqlite3.Connection:
    init_db(db)
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        INSERT INTO aliases (id, market, alias, n_posts) VALUES
          (1, 'silkroad1', 'Nightcrawler', 10),
          (2, 'agora', 'Nightcrawler', 8),
          (3, 'silkroad1', 'VendorA', 20),
          (4, 'silkroad1', 'VendorB', 20),
          (5, 'silkroad1', 'VendorC', 5),
          (6, 'agora', 'Unrelated', 5);
        INSERT INTO posts (
          market, msg_id, alias, thread_id, body, raw_html,
          source_archive, scrape_date, source_member_path, content_sha256
        ) VALUES
          ('silkroad1', 1, 'VendorA', 99, 'lsd', 'x', 'a.tar.xz', '2014-01-01', 'm1', 'aa'),
          ('silkroad1', 2, 'VendorB', 99, 'lsd', 'x', 'a.tar.xz', '2014-01-01', 'm2', 'bb'),
          ('silkroad1', 3, 'VendorC', 99, 'lsd', 'x', 'a.tar.xz', '2014-01-01', 'm3', 'cc');
        INSERT INTO evidence (alias_id, post_id, kind, value) VALUES
          (3, 1, 'pgp_fpr', 'AAAAAAAA'),
          (5, 3, 'pgp_fpr', 'AAAAAAAA');
        """
    )
    conn.commit()
    return conn


def test_known_same_username_is_positive(tmp_path: Path):
    db = tmp_path / "l.sqlite"
    _seed(db).close()
    summary = generate_labels(db)
    assert summary["positives"] == 1
    with sqlite3.connect(db) as conn:
        row = conn.execute(
            "SELECT label, source, a_alias, b_alias, a_market, b_market "
            "FROM label_pairs WHERE source = 'same_username'"
        ).fetchone()
    assert row[0] == 1
    assert row[1] == "same_username"
    assert {row[2], row[3]} == {"Nightcrawler"}
    assert {row[4], row[5]} == {"agora", "silkroad1"}


def test_hard_negative_never_shares_evidence(tmp_path: Path):
    db = tmp_path / "l.sqlite"
    _seed(db).close()
    generate_labels(db)
    with sqlite3.connect(db) as conn:
        hards = conn.execute(
            "SELECT a_alias_id, b_alias_id, a_alias, b_alias FROM label_pairs "
            "WHERE source = 'hard_neg'"
        ).fetchall()
        assert hards
        shared = {
            (min(a, b), max(a, b))
            for a, b in conn.execute(
                """
                SELECT e1.alias_id, e2.alias_id
                FROM evidence e1
                JOIN evidence e2
                  ON e1.kind = e2.kind AND e1.value = e2.value
                 AND e1.alias_id < e2.alias_id
                """
            )
        }
        for a, b, *_ in hards:
            assert (min(a, b), max(a, b)) not in shared


def test_jack_n_hoff_is_a_real_corpus_positive():
    db = Path("data/db/attrib.sqlite")
    if not db.is_file():
        return
    with sqlite3.connect(db) as conn:
        markets = {
            r[0]
            for r in conn.execute(
                "SELECT market FROM aliases WHERE alias = ?",
                (KNOWN_CORPUS_ALIAS,),
            )
        }
        assert KNOWN_MARKETS[0] in markets and KNOWN_MARKETS[1] in markets
        tables = {
            r[0]
            for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        if "label_pairs" not in tables:
            return
        hit = conn.execute(
            """
            SELECT COUNT(*) FROM label_pairs
            WHERE label = 1 AND source = 'same_username'
              AND a_alias = ? AND b_alias = ?
              AND a_market IN (?, ?) AND b_market IN (?, ?)
              AND a_market != b_market
            """,
            (KNOWN_CORPUS_ALIAS, KNOWN_CORPUS_ALIAS, *KNOWN_MARKETS, *KNOWN_MARKETS),
        ).fetchone()[0]
        assert hit >= 1
