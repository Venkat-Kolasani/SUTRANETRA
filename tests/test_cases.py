"""Cases are isolated; identical canonical config hashes identically."""

import sqlite3
from pathlib import Path

from src.ingest.schema import init_db
from src.opsec.scanner import list_findings, persist_findings
from src.pipeline.case import config_hash, create_case, get_case, set_status

CFG = {
    "profile": "dev",
    "markets": ["silkroad1", "thehub"],
    "fusion": {"confidence_threshold": 0.83},
    "stylometry": {"blocking_top_k": 50},
}


def test_two_cases_do_not_clobber(tmp_path: Path):
    db = tmp_path / "c.sqlite"
    init_db(db)
    a = create_case(db, CFG, case_id="CASE-A", threshold=0.83)
    b = create_case(db, CFG, case_id="CASE-B", threshold=0.70)
    assert a["threshold"] == 0.83
    assert b["threshold"] == 0.70
    assert a["config_hash"] == b["config_hash"] == config_hash(CFG)
    with sqlite3.connect(db) as conn:
        conn.execute(
            "INSERT INTO pair_scores (case_id, a_alias_id, b_alias_id, confidence) "
            "VALUES ('CASE-A', 1, 2, 0.91), ('CASE-B', 1, 2, 0.40)"
        )
        conn.commit()
        only_a = conn.execute(
            "SELECT confidence FROM pair_scores WHERE case_id='CASE-A'"
        ).fetchall()
        only_b = conn.execute(
            "SELECT confidence FROM pair_scores WHERE case_id='CASE-B'"
        ).fetchall()
    assert only_a == [(0.91,)]
    assert only_b == [(0.40,)]
    set_status(db, "CASE-A", "running")
    set_status(db, "CASE-A", "complete")
    assert get_case(db, "CASE-A")["status"] == "complete"
    assert get_case(db, "CASE-B")["status"] == "created"


def test_opsec_findings_are_case_scoped(tmp_path: Path):
    db = tmp_path / "c.sqlite"
    init_db(db)
    create_case(db, CFG, case_id="CASE-A", threshold=0.83)
    create_case(db, CFG, case_id="CASE-B", threshold=0.70)
    persist_findings(
        db,
        "CASE-A",
        "http://127.0.0.1:8080",
        [{"finding_kind": "clearnet_ref", "value": "erowid.org", "detail": "img"}],
    )
    assert [r["value"] for r in list_findings(db, "CASE-A")] == ["erowid.org"]
    assert list_findings(db, "CASE-B") == []


def test_config_hash_ignores_paths():
    a = dict(CFG)
    b = {**CFG, "paths": {"sqlite_db": "/tmp/other.sqlite"}}
    assert config_hash(a) == config_hash(b)
