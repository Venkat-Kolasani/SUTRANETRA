"""Evidence Trail order, lineage, and no fabricated OpSec/CT steps."""

import sqlite3
from pathlib import Path

from src.explain.trail import build_evidence_trail
from src.ingest.schema import init_db
from src.pipeline.case import create_case

CFG = {
    "profile": "dev",
    "markets": ["silkroad1", "agora"],
    "fusion": {"confidence_threshold": 0.83},
    "stylometry": {"blocking_top_k": 50},
}

FPR = "A1B2C3D4E5F60718293A4B5C6D7E8F9012349F00"
SHA_A = "a" * 64
SHA_B = "b" * 64


def _seed(db: Path, *, with_ct: bool) -> tuple[int, int]:
    init_db(db)
    create_case(db, CFG, case_id="CASE-T", threshold=0.83)
    with sqlite3.connect(db) as conn:
        conn.executemany(
            """
            INSERT INTO posts (
              id, market, msg_id, alias, body, raw_html,
              source_archive, scrape_date, source_member_path, content_sha256
            ) VALUES (?,?,?,?,?,?,?,?,?,?)
            """,
            [
                (
                    10,
                    "silkroad1",
                    1,
                    "alice",
                    "pgp",
                    "<p>pgp</p>",
                    "silkroad1-forums.tar.xz",
                    "2014-11-25",
                    "silkroad1-forums/2014-11-25/index.php?topic=1.0",
                    SHA_A,
                ),
                (
                    20,
                    "agora",
                    2,
                    "bob",
                    "pgp",
                    "<p>pgp</p>",
                    "agora-forums.tar.xz",
                    "2014-12-01",
                    "agora-forums/2014-12-01/index.php?topic=2.0",
                    SHA_B,
                ),
            ],
        )
        conn.executemany(
            "INSERT INTO aliases (id, market, alias, n_posts) VALUES (?,?,?,?)",
            [(1, "silkroad1", "alice", 12), (2, "agora", "bob", 7)],
        )
        conn.executemany(
            "INSERT INTO evidence (id, alias_id, post_id, kind, value) VALUES (?,?,?,?,?)",
            [
                (100, 1, 10, "pgp_fpr", FPR),
                (101, 2, 20, "pgp_fpr", FPR),
                (102, 1, 10, "clearnet", "erowid.org"),
            ],
        )
        conn.execute(
            """
            INSERT INTO pair_scores (
              case_id, a_alias_id, b_alias_id,
              s_char, s_embed, s_hard, s_time, n_shared_hard, confidence
            ) VALUES ('CASE-T', 1, 2, 0.74, 0.20, 0.875, 0.81, 2, 0.91)
            """
        )
        conn.execute(
            "INSERT INTO clusters (case_id, cluster_id, alias_id, confidence) "
            "VALUES ('CASE-T', 1, 1, 0.91), ('CASE-T', 1, 2, 0.91)"
        )
        if with_ct:
            conn.executemany(
                """
                INSERT INTO opsec_findings (case_id, target, finding_kind, value, detail, created_at)
                VALUES ('CASE-T', ?, ?, ?, ?, '2026-09-05T00:00:00Z')
                """,
                [
                    ("http://127.0.0.1:8080", "clearnet_ref", "erowid.org", "img"),
                    (
                        "ct:erowid.org",
                        "ct_sibling",
                        "archive.erowid.org",
                        '{"seed":"erowid.org","source":"cache"}',
                    ),
                ],
            )
        conn.commit()
    return 1, 2


def test_trail_order_lineage_and_optional_ct(tmp_path: Path):
    db = tmp_path / "t.sqlite"
    _seed(db, with_ct=True)
    trail = build_evidence_trail(db, "CASE-T", a_alias_id=1, b_alias_id=2)
    types = [s["type"] for s in trail]
    assert types == [
        "alias",
        "post",
        "evidence",
        "alias",
        "post",
        "score",
        "opsec",
        "ct_domain",
    ]
    posts = [s for s in trail if s["type"] == "post"]
    assert posts[0]["source_archive"] == "silkroad1-forums.tar.xz"
    assert posts[0]["scrape_date"] == "2014-11-25"
    assert posts[0]["source_member_path"].endswith("topic=1.0")
    assert posts[0]["content_sha256"] == SHA_A
    assert posts[1]["source_archive"] == "agora-forums.tar.xz"
    assert posts[1]["content_sha256"] == SHA_B
    assert trail[2]["kind"] == "pgp_fpr"
    assert trail[-2]["type"] == "opsec"
    assert trail[-1]["type"] == "ct_domain"
    assert trail[-1]["value"] == "archive.erowid.org"
    idx_clear = types.index("opsec")
    assert types.index("ct_domain") > idx_clear


def test_no_fabricated_opsec_when_absent(tmp_path: Path):
    db = tmp_path / "n.sqlite"
    _seed(db, with_ct=False)
    trail = build_evidence_trail(db, "CASE-T", cluster_id=1)
    types = [s["type"] for s in trail]
    assert "opsec" not in types
    assert "ct_cert" not in types
    assert "ct_domain" not in types
    assert types[-1] == "score"
    assert any(s["type"] == "post" and s["content_sha256"] == SHA_A for s in trail)
