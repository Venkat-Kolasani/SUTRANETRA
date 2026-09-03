"""Newest scrape wins for (market, msg_id), including lineage fields."""

from __future__ import annotations

import io
import tarfile
from pathlib import Path

from src.ingest.load import load_archive

FIXTURES = Path(__file__).parent / "fixtures"
OLD_HTML = FIXTURES / "topic_440_2014-11-18.html"
NEW_HTML = FIXTURES / "topic_440_2014-11-25.html"
OLD_MEMBER = "cannabisroad3-forums/2014-11-18/index.php?topic=440.0"
NEW_MEMBER = "cannabisroad3-forums/2014-11-25/index.php?topic=440.0"


def _topic_tar(path: Path) -> Path:
    with tarfile.open(path, "w:xz") as tar:
        for member, src in ((OLD_MEMBER, OLD_HTML), (NEW_MEMBER, NEW_HTML)):
            data = src.read_bytes()
            info = tarfile.TarInfo(member)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return path


def test_newest_scrape_wins_lineage(tmp_path: Path):
    archive = _topic_tar(tmp_path / "dedupe.tar.xz")
    db = tmp_path / "attrib.sqlite"
    summary = load_archive(archive, db, "cannabisroad3")
    assert summary["posts_parsed"] == 30  # 15 posts × 2 scrape dates
    assert summary["posts_loaded"] == 15

    import sqlite3

    with sqlite3.connect(db) as conn:
        conn.row_factory = sqlite3.Row
        n = conn.execute("SELECT COUNT(*) AS c FROM posts").fetchone()["c"]
        assert n == 15
        row = conn.execute(
            "SELECT * FROM posts WHERE market = ? AND msg_id = ?",
            ("cannabisroad3", 4111),
        ).fetchone()
        assert row["scrape_date"] == "2014-11-25"
        assert row["source_member_path"] == NEW_MEMBER
        assert row["source_archive"] == "dedupe.tar.xz"
        from src.ingest.smf_parser import content_sha256

        assert row["content_sha256"] == content_sha256(row["raw_html"])
        assert row["alias"] == "AngelEyes"
