"""Export writers produce CSV / JSON / PDF with trail + provenance."""

import csv
import json
import sqlite3
from pathlib import Path

import networkx as nx

from src.export.writers import (
    search_corpus,
    write_clusters_csv,
    write_report_json,
    write_report_pdf,
)
from src.explain.trail import build_evidence_trail
from src.graph.build import cluster_report
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


def _seed(db: Path) -> None:
    init_db(db)
    create_case(db, CFG, case_id="CASE-X", threshold=0.83)
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
            [
                (1, "silkroad1", "alice", 12),
                (2, "agora", "bob", 7),
                (3, "nucleus", "businessglobal", 4),
            ],
        )
        conn.executemany(
            "INSERT INTO evidence (id, alias_id, post_id, kind, value) VALUES (?,?,?,?,?)",
            [
                (100, 1, 10, "pgp_fpr", FPR),
                (101, 2, 20, "pgp_fpr", FPR),
            ],
        )
        conn.execute(
            """
            INSERT INTO pair_scores (
              case_id, a_alias_id, b_alias_id,
              s_char, s_embed, s_hard, s_time, n_shared_hard, confidence
            ) VALUES ('CASE-X', 1, 2, 0.74, 0.20, 0.875, 0.81, 1, 0.91)
            """
        )
        conn.execute(
            "INSERT INTO clusters (case_id, cluster_id, alias_id, confidence) "
            "VALUES ('CASE-X', 1, 1, 0.91), ('CASE-X', 1, 2, 0.91), "
            "('CASE-X', 1, 3, 0.91)"
        )
        conn.commit()


def test_export_writers_structure(tmp_path: Path):
    db = tmp_path / "x.sqlite"
    _seed(db)
    trail = build_evidence_trail(db, "CASE-X", cluster_id=1)
    assert any(s["type"] == "post" and s["content_sha256"] == SHA_A for s in trail)

    with sqlite3.connect(db) as conn:
        conn.row_factory = sqlite3.Row
        hits = search_corpus(conn, "alice")
    assert hits
    assert hits[0]["alias"] == "alice"
    assert hits[0]["content_sha256"] == SHA_A
    assert hits[0]["source_archive"] == "silkroad1-forums.tar.xz"
    assert hits[0]["source_member_path"]

    csv_path = tmp_path / "clusters.csv"
    write_clusters_csv(db, "CASE-X", csv_path)
    with csv_path.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert rows
    assert set(rows[0]) == {
        "case_id",
        "cluster_id",
        "alias",
        "market",
        "n_posts",
        "confidence",
        "evidence_summary",
    }
    assert rows[0]["case_id"] == "CASE-X"

    json_path = tmp_path / "report.json"
    write_report_json(db, "CASE-X", json_path)
    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert data["system"] == "SUTRANETRA"
    assert data["clusters"]
    cluster = data["clusters"][0]
    assert cluster["evidence_trail"]
    assert cluster["evidence_trail"][0]["type"] == "alias"
    posts = [s for s in cluster["evidence_trail"] if s["type"] == "post"]
    assert posts[0]["source_archive"] == "silkroad1-forums.tar.xz"
    assert posts[0]["content_sha256"] == SHA_A
    assert cluster["explanation"]["template_sentence"]

    pdf_path = tmp_path / "report.pdf"
    write_report_pdf(db, "CASE-X", pdf_path)
    assert pdf_path.exists()
    assert pdf_path.stat().st_size > 500

    g = nx.Graph()
    g.add_node("silkroad1:alice", alias_id=1, market="silkroad1")
    with sqlite3.connect(db) as conn:
        conn.row_factory = sqlite3.Row
        rep = cluster_report(
            conn,
            g,
            ["silkroad1:alice", "nucleus:businessglobal"],
            1,
            {},
            {},
        )
    assert "nucleus:businessglobal" not in [m["node"] for m in rep["members"]]
    assert rep["n_members"] == 2
