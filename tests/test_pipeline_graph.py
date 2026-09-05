"""LangGraph wrapper: e2e on a tiny DB, checkpoint resume, parallel timings."""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

import yaml

from src.explain.trail import build_evidence_trail
from src.fusion.labels import LABEL_SCHEMA
from src.ingest.schema import init_db
from src.pipeline.graph import (
    compiled_app,
    export_architecture_png,
    invoke_pipeline,
)

CFG = {
    "profile": "dev",
    "paths": {"data_raw": "data/raw", "sqlite_db": "unused.sqlite", "ct_cache": "data/cache/ct"},
    "markets": ["silkroad1", "silkroad2"],
    "fusion": {"confidence_threshold": 0.50},
    "stylometry": {
        "char_ngram_min_df": 1,
        "char_ngram_max_features": 2000,
        "blocking_top_k": 8,
        "blocking_svd_dims": 8,
        "embed_max_posts": 20,
        "embed_batch_size": 8,
        "embedding_model": "sentence-transformers/all-MiniLM-L6-v2",
    },
}

PGP = (Path(__file__).parent / "fixtures" / "pgp_trappy_msg1596.asc").read_text(
    encoding="utf-8"
)


def _post(pid, market, msg_id, alias, body, ts="2014-01-01 12:00:00"):
    return (
        pid,
        market,
        msg_id,
        alias,
        body,
        body,
        f"{market}-forums.tar.xz",
        "2014-01-01",
        f"{market}-forums/2014-01-01/index.php?topic={msg_id}.0",
        f"{pid:064x}"[:64],
        ts,
    )


def seed(db: Path) -> None:
    init_db(db)
    with sqlite3.connect(db) as conn:
        conn.executescript(LABEL_SCHEMA)
        posts = []
        aliases = []
        aid = 1
        pid = 1
        # 8 same-handle cross-market positives + 8 distinct-handle negatives
        for i in range(8):
            name = f"vendor{i}"
            body = (f"ships overnight pgp {PGP} cannabis grams quality " * 4) + f" sig{i}"
            posts.append(_post(pid, "silkroad1", 100 + i, name, body))
            pid += 1
            posts.append(_post(pid, "silkroad2", 200 + i, name, body))
            pid += 1
            aliases.append((aid, "silkroad1", name, 12))
            aliases.append((aid + 1, "silkroad2", name, 12))
            conn.execute(
                "INSERT INTO label_pairs (a_alias_id,b_alias_id,a_market,a_alias,b_market,b_alias,label,source) "
                "VALUES (?,?,?,?,?,?,1,'same_username')",
                (aid, aid + 1, "silkroad1", name, "silkroad2", name),
            )
            aid += 2
        for i in range(8):
            a, b = f"negA{i}", f"negB{i}"
            posts.append(_post(pid, "silkroad1", 300 + i, a, f"totally different topic widgets {i} " * 8))
            pid += 1
            posts.append(_post(pid, "silkroad2", 400 + i, b, f"unrelated electronics review {i} " * 8))
            pid += 1
            aliases.append((aid, "silkroad1", a, 12))
            aliases.append((aid + 1, "silkroad2", b, 12))
            conn.execute(
                "INSERT INTO label_pairs (a_alias_id,b_alias_id,a_market,a_alias,b_market,b_alias,label,source) "
                "VALUES (?,?,?,?,?,?,0,'random_neg')",
                (aid, aid + 1, "silkroad1", a, "silkroad2", b),
            )
            aid += 2
        conn.executemany(
            """
            INSERT INTO posts (
              id, market, msg_id, alias, body, raw_html,
              source_archive, scrape_date, source_member_path, content_sha256, ts
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """,
            posts,
        )
        conn.executemany(
            "INSERT INTO aliases (id, market, alias, n_posts) VALUES (?,?,?,?)",
            aliases,
        )
        conn.commit()


def _write_cfg(tmp: Path, db: Path) -> Path:
    cfg = dict(CFG)
    cfg["paths"] = dict(CFG["paths"])
    cfg["paths"]["sqlite_db"] = str(db)
    path = tmp / "config.yaml"
    path.write_text(yaml.dump(cfg), encoding="utf-8")
    return path


def test_graph_e2e_matches_standalone_trail(tmp_path: Path, monkeypatch):
    db = tmp_path / "p.sqlite"
    seed(db)
    cfg_path = _write_cfg(tmp_path, db)
    ckpt = tmp_path / "ckpt.sqlite"
    import src.stylometry.embed as embed

    def fake_embed(db_path, sty=None):
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS pair_channel_scores (
                  a_alias_id INTEGER NOT NULL,
                  b_alias_id INTEGER NOT NULL,
                  s_embed REAL,
                  s_time REAL,
                  PRIMARY KEY (a_alias_id, b_alias_id)
                )
                """
            )
        return {}

    monkeypatch.setattr(embed, "run", fake_embed)
    out = invoke_pipeline(
        db,
        "CASE-G",
        config_path=str(cfg_path),
        checkpoint_path=ckpt,
        markets=["silkroad1", "silkroad2"],
        heuristic=True,
    )
    assert out["case_id"] == "CASE-G"
    assert out["n_posts"] >= 16
    assert out["n_evidence"] >= 1
    assert out["scored_pairs"] >= 1
    assert out["clusters"]
    trail = out["evidence_trail"]
    assert trail
    standalone = build_evidence_trail(db, "CASE-G", cluster_id=1)
    assert [s["type"] for s in standalone] == [s["type"] for s in trail]
    with sqlite3.connect(db) as conn:
        status = conn.execute(
            "SELECT status FROM cases WHERE case_id='CASE-G'"
        ).fetchone()[0]
    assert status == "complete"


def test_checkpoint_resume_skips_completed_ingest(tmp_path: Path, monkeypatch):
    db = tmp_path / "r.sqlite"
    seed(db)
    cfg_path = _write_cfg(tmp_path, db)
    ckpt = tmp_path / "resume.sqlite"
    calls = {"ingest": 0}

    import src.ingest.load as load

    real = load.run

    def counted(db_path, cfg, *, markets=None):
        calls["ingest"] += 1
        return real(db_path, cfg, markets=markets)

    monkeypatch.setattr(load, "run", counted)

    import src.stylometry.embed as embed
    import src.temporal.activity as temporal
    import src.fusion.model as fusion_mod
    import src.graph.build as graph_mod
    import src.explain.trail as trail_mod
    import src.opsec.scanner as scanner

    monkeypatch.setattr(embed, "run", lambda *a, **k: {})
    monkeypatch.setattr(temporal, "run", lambda *a, **k: {})
    monkeypatch.setattr(fusion_mod, "run", lambda *a, **k: {"n_scored": 0})
    monkeypatch.setattr(graph_mod, "run", lambda *a, **k: {"multi_market": []})
    monkeypatch.setattr(trail_mod, "build_evidence_trail", lambda *a, **k: [])
    monkeypatch.setattr(scanner, "scan_corpus", lambda *a, **k: [])
    monkeypatch.setattr(scanner, "persist_findings", lambda *a, **k: 0)
    monkeypatch.setattr(scanner, "list_findings", lambda *a, **k: [])
    initial = {
        "case_id": "CASE-R",
        "db_path": str(db),
        "config_path": str(cfg_path),
        "markets": ["silkroad1"],
        "heuristic": True,
        "errors": [],
        "timings": [],
    }
    cfg = {"configurable": {"thread_id": "CASE-R"}}
    with compiled_app(ckpt, interrupt_after=["ingest"]) as app:
        app.invoke(initial, cfg)
        assert calls["ingest"] == 1
        app.invoke(None, cfg)
        assert calls["ingest"] == 1


def test_opsec_and_stylometry_overlap(tmp_path: Path, monkeypatch):
    db = tmp_path / "t.sqlite"
    seed(db)
    cfg_path = _write_cfg(tmp_path, db)

    import src.stylometry.char_ngram as char
    import src.stylometry.embed as embed
    import src.temporal.activity as temporal
    import src.opsec.scanner as scanner

    def sleepy_char(db_path, sty):
        time.sleep(0.40)
        return {"n_candidates": 1}

    def sleepy_opsec_scan(conn, limit=50):
        time.sleep(0.40)
        return []

    monkeypatch.setattr(char, "run", sleepy_char)
    monkeypatch.setattr(embed, "run", lambda *a, **k: {})
    monkeypatch.setattr(temporal, "run", lambda *a, **k: {})
    monkeypatch.setattr(scanner, "scan_corpus", sleepy_opsec_scan)
    monkeypatch.setattr(scanner, "persist_findings", lambda *a, **k: 0)
    monkeypatch.setattr(scanner, "list_findings", lambda *a, **k: [])

    import src.fusion.model as fusion_mod
    import src.graph.build as graph_mod
    import src.explain.trail as trail_mod

    monkeypatch.setattr(fusion_mod, "run", lambda *a, **k: {"n_scored": 0})
    monkeypatch.setattr(graph_mod, "run", lambda *a, **k: {"multi_market": []})
    monkeypatch.setattr(trail_mod, "build_evidence_trail", lambda *a, **k: [])

    out = invoke_pipeline(
        db,
        "CASE-P",
        config_path=str(cfg_path),
        checkpoint_path=tmp_path / "p.ckpt.sqlite",
        heuristic=True,
    )
    by = {t["node"]: t for t in out["timings"]}
    sty, op = by["stylometry"], by["opsec"]
    overlap = min(sty["t1"], op["t1"]) - max(sty["t0"], op["t0"])
    assert overlap > 0.2, (sty, op, overlap)


def test_architecture_png_from_compiled_graph(tmp_path: Path):
    dest = Path("docs/architecture.png")
    export_architecture_png(dest)
    assert dest.is_file() and dest.stat().st_size > 500
    mermaid = (
        __import__("src.pipeline.graph", fromlist=["build_graph"])
        .build_graph()
        .compile()
        .get_graph()
        .draw_mermaid()
    )
    compact = mermaid.replace(" ", "").replace("\n", "")
    for name in ("ingest", "evidence", "stylometry", "fusion", "graph", "opsec", "explain"):
        assert name in mermaid
    assert "evidence-->stylometry" in compact or "evidence-->stylometry;" in compact
    assert "evidence-->opsec" in compact
    assert "opsec-->explain" in compact
    assert "graph-->explain" in compact
