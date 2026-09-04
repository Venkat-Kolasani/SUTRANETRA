"""Dedupe and lineage stay stable across two consecutive multi-market loads."""

from __future__ import annotations

import io
import sqlite3
import tarfile
from pathlib import Path

from src.ingest.load import load_archive
from src.ingest.smf_parser import content_sha256

FIXTURES = Path(__file__).parent / "fixtures"
SMF_HTML = FIXTURES / "topic_440_2014-11-25.html"
SMF_MEMBER = "cannabisroad3-forums/2014-11-25/index.php?topic=440.0"
PHPBB_HTML = FIXTURES / "nucleus_viewtopic_10_2014-10-24.html"
PHPBB_MEMBER = "nucleus-forums/2014-10-24/viewtopic.php?id=10"


def _one_page_tar(path: Path, member: str, src: Path) -> Path:
    data = src.read_bytes()
    with tarfile.open(path, "w:xz") as tar:
        info = tarfile.TarInfo(member)
        info.size = len(data)
        tar.addfile(info, io.BytesIO(data))
    return path


def _counts(db: Path) -> tuple[int, int, int]:
    with sqlite3.connect(db) as conn:
        posts = conn.execute("SELECT COUNT(*) FROM posts").fetchone()[0]
        aliases = conn.execute("SELECT COUNT(*) FROM aliases").fetchone()[0]
        markets = conn.execute("SELECT COUNT(DISTINCT market) FROM posts").fetchone()[0]
        return posts, aliases, markets


def test_two_market_load_is_stable_and_lineage_non_null(tmp_path: Path):
    smf_tar = _one_page_tar(tmp_path / "cr3.tar.xz", SMF_MEMBER, SMF_HTML)
    phpbb_tar = _one_page_tar(tmp_path / "nuc.tar.xz", PHPBB_MEMBER, PHPBB_HTML)
    db = tmp_path / "attrib.sqlite"

    load_archive(smf_tar, db, "cannabisroad3")
    load_archive(phpbb_tar, db, "nucleus")
    first = _counts(db)
    assert first[2] == 2

    load_archive(smf_tar, db, "cannabisroad3")
    load_archive(phpbb_tar, db, "nucleus")
    assert _counts(db) == first

    with sqlite3.connect(db) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM posts").fetchall()
        assert rows
        for row in rows:
            assert row["source_archive"]
            assert row["scrape_date"]
            assert row["source_member_path"]
            assert row["content_sha256"]
            assert row["raw_html"]
            assert row["content_sha256"] == content_sha256(row["raw_html"])
