"""Cloud API wrapper + Groq-down polish fallback."""

from __future__ import annotations

import inspect
import json
import os
from pathlib import Path

import pytest
import yaml

from src.explain.reason import template_sentence
from src.ingest.schema import init_db
from src.llm.polish import polish_explanation


def _seed(db: Path) -> None:
    init_db(db)
    import sqlite3

    conn = sqlite3.connect(db)
    conn.executescript(
        """
        INSERT INTO aliases (id, market, alias, n_posts) VALUES
          (1, 'silkroad1', 'nihilist23', 10),
          (2, 'silkroad1', 'nxxxxxxx23', 8);
        INSERT INTO posts (
          id, market, msg_id, alias, body, raw_html,
          source_archive, scrape_date, source_member_path, content_sha256
        ) VALUES (
          1, 'silkroad1', 1, 'nihilist23', 'pgp here', '<p>',
          'sr.tar.xz', '2014-01-01', 'a.html', 'abc'
        );
        INSERT INTO evidence (id, alias_id, post_id, kind, value, context) VALUES
          (1, 1, 1, 'pgp_fpr', 'DEADBEEF', ''),
          (2, 2, 1, 'pgp_fpr', 'DEADBEEF', '');
        INSERT INTO cases (
          case_id, created_at, corpus_snapshot, config_hash, model_version, threshold, status
        ) VALUES (
          'CASE-2026-001', '2026-01-01T00:00:00Z',
          '{"markets":["silkroad1"],"n_posts":1,"n_aliases":2}',
          'abc', 'test', 0.83, 'complete'
        );
        INSERT INTO pair_scores (
          case_id, a_alias_id, b_alias_id, s_char, s_embed, s_hard, s_time,
          n_shared_hard, confidence, reason
        ) VALUES (
          'CASE-2026-001', 1, 2, 0.4, 0.5, 0.9, 0.3, 1, 0.85, 'shared_pgp'
        );
        INSERT INTO clusters (case_id, cluster_id, alias_id, confidence) VALUES
          ('CASE-2026-001', 1, 1, 0.85),
          ('CASE-2026-001', 1, 2, 0.85);
        INSERT INTO opsec_findings (case_id, target, finding_kind, value, detail, created_at)
          VALUES ('CASE-2026-001', 'http://127.0.0.1:8080', 'clearnet_ref', 'erowid.org', '', '2026-01-01');
        """
    )
    conn.commit()
    conn.close()


@pytest.fixture()
def cloud_env(tmp_path, monkeypatch):
    db = tmp_path / "demo.sqlite"
    _seed(db)
    monkeypatch.setenv("SUTRANETRA_PROFILE", "cloud")
    monkeypatch.setenv("SUTRANETRA_SQLITE", str(db))
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.setenv("SUTRANETRA_CORS_ORIGINS", "*")
    return db


def test_polish_signature_is_structured_dict_only():
    sig = inspect.signature(polish_explanation)
    params = list(sig.parameters)
    assert params[0] == "evidence"
    assert "conn" not in params
    assert "db" not in params
    assert "post" not in params


def test_polish_groq_down_returns_template(cloud_env):
    ev = {
        "a": {"alias": "nihilist23", "market": "silkroad1", "n_posts": 10},
        "b": {"alias": "nxxxxxxx23", "market": "silkroad1", "n_posts": 8},
        "confidence": 0.85,
        "reason": "shared_pgp",
        "s_char": 0.4,
        "s_embed": 0.5,
        "s_hard": 0.9,
        "s_time": 0.3,
        "shared_evidence": [{"kind": "pgp_fpr", "value": "DEADBEEF", "n_posts": 1}],
        "timezone": {},
        "framing": "x",
        "system": "SUTRANETRA",
    }
    with open("config.yaml", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    out = polish_explanation(ev, cfg)
    assert out == template_sentence(ev)
    assert "DEADBEEF" in out or "DEADBE" in out


def test_api_health_and_cluster(cloud_env):
    from fastapi.testclient import TestClient

    from src.api.app import app

    client = TestClient(app)
    h = client.get("/health")
    assert h.status_code == 200
    body = h.json()
    assert body["ok"] is True
    assert "llm" in body
    assert body["llm"]["provider"] in ("groq", "ollama")
    clusters = client.get("/cases/CASE-2026-001/clusters")
    assert clusters.status_code == 200
    body = clusters.json()
    assert body[0]["cluster_id"] == 1
    assert body[0]["n_members"] == 2


def test_index_is_website_not_streamlit(cloud_env):
    from fastapi.testclient import TestClient

    from src.api.app import app

    r = TestClient(app).get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers.get("content-type", "")
    assert "SUTRANETRA" in r.text
    assert "streamlit" not in r.text.lower()
    docs = TestClient(app).get("/docs", follow_redirects=False)
    assert docs.status_code in (307, 302)
    assert docs.headers["location"] == "/"


def test_agent_groq_down_degrades(cloud_env):
    from src.agent.investigator import ask

    with open("config.yaml", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    out = ask("hello", db_path=cloud_env, case_id="CASE-2026-001", cfg=cfg)
    assert out["degraded"] is True
    assert out["ok"] is False
    assert out["text"] == ""
