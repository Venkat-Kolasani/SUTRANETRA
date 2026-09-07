"""One-shot cloud path check. python tests/run_cloud_check.py"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import yaml

from src.explain.reason import template_sentence
from src.ingest.schema import init_db
from src.llm.polish import polish_explanation


def seed(db: Path) -> None:
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
        """
    )
    conn.commit()
    conn.close()


def main() -> None:
    db = Path(tempfile.mkdtemp()) / "demo.sqlite"
    seed(db)
    os.environ["SUTRANETRA_PROFILE"] = "cloud"
    os.environ["SUTRANETRA_SQLITE"] = str(db)
    os.environ.pop("GROQ_API_KEY", None)
    print("seeded")
    ev = {
        "a": {"alias": "nihilist23", "market": "silkroad1", "n_posts": 10},
        "b": {"alias": "nxxxxxxx23", "market": "silkroad1", "n_posts": 8},
        "confidence": 0.85,
        "reason": "shared_pgp",
        "s_char": 0.4,
        "shared_evidence": [{"kind": "pgp_fpr", "value": "DEADBEEF", "n_posts": 1}],
        "timezone": {},
    }
    cfg = yaml.safe_load(open("config.yaml", encoding="utf-8"))
    assert polish_explanation(ev, cfg) == template_sentence(ev)
    print("polish ok")
    from fastapi.testclient import TestClient

    from src.api.app import app

    client = TestClient(app)
    assert client.get("/health").json()["ok"] is True
    body = client.get("/cases/CASE-2026-001/clusters").json()
    assert body[0]["n_members"] == 2
    print("api ok")
    from src.agent.investigator import ask

    assert ask("hello", db_path=db, case_id="CASE-2026-001", cfg=cfg)["degraded"] is True
    print("agent degrade ok")


if __name__ == "__main__":
    main()
