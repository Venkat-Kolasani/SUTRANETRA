"""Lineage columns are written at ingest and joinable from evidence."""

from __future__ import annotations

import io
import sqlite3
import tarfile
from pathlib import Path

from src.ingest.load import load_archive
from src.ingest.smf_parser import content_sha256

FIXTURE = Path(__file__).parent / "fixtures" / "topic_440_2014-11-25.html"
MEMBER = "cannabisroad3-forums/2014-11-25/index.php?topic=440.0"


def test_lineage_non_null_hash_matches_and_evidence_join(tmp_path: Path):
    archive = tmp_path / "prov.tar.xz"
    data = FIXTURE.read_bytes()
    with tarfile.open(archive, "w:xz") as tar:
        info = tarfile.TarInfo(MEMBER)
        info.size = len(data)
        tar.addfile(info, io.BytesIO(data))

    db = tmp_path / "attrib.sqlite"
    load_archive(archive, db, "cannabisroad3")

    with sqlite3.connect(db) as conn:
        conn.row_factory = sqlite3.Row
        posts = conn.execute("SELECT * FROM posts").fetchall()
        assert posts
        for row in posts:
            assert row["source_archive"]
            assert row["scrape_date"]
            assert row["source_member_path"]
            assert row["content_sha256"]
            assert row["raw_html"]
            assert row["content_sha256"] == content_sha256(row["raw_html"])

        sample = conn.execute(
            "SELECT id, alias FROM posts WHERE msg_id = 4111"
        ).fetchone()
        alias_id = conn.execute(
            "SELECT id FROM aliases WHERE market = ? AND alias = ?",
            ("cannabisroad3", sample["alias"]),
        ).fetchone()["id"]
        conn.execute(
            "INSERT INTO evidence (alias_id, post_id, kind, value, context) VALUES (?,?,?,?,?)",
            (alias_id, sample["id"], "onion", "forumz2gljo2vhzb.onion", "test"),
        )
        joined = conn.execute(
            """
            SELECT p.source_archive, p.scrape_date, p.source_member_path, p.content_sha256
            FROM evidence e
            JOIN posts p ON p.id = e.post_id
            WHERE e.kind = 'onion'
            """
        ).fetchone()
        assert joined["source_archive"] == "prov.tar.xz"
        assert joined["scrape_date"] == "2014-11-25"
        assert joined["source_member_path"] == MEMBER
        assert joined["content_sha256"]
