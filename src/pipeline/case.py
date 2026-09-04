"""Investigation case ledger (SPEC.md §6.2)."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def canonical_config(cfg: dict) -> dict:
    """Scoring-relevant keys only — no machine-local paths."""
    sty = dict(cfg.get("stylometry") or {})
    return {
        "profile": cfg.get("profile"),
        "markets": list(cfg.get("markets") or []),
        "fusion": dict(cfg.get("fusion") or {}),
        "stylometry": sty,
    }


def config_hash(cfg: dict) -> str:
    blob = json.dumps(canonical_config(cfg), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode()).hexdigest()


def corpus_snapshot(conn: sqlite3.Connection) -> str:
    markets = [
        r[0]
        for r in conn.execute(
            "SELECT DISTINCT market FROM posts ORDER BY market"
        )
    ]
    n_posts = conn.execute("SELECT COUNT(*) FROM posts").fetchone()[0]
    n_aliases = conn.execute("SELECT COUNT(*) FROM aliases").fetchone()[0]
    return json.dumps(
        {"markets": markets, "n_posts": n_posts, "n_aliases": n_aliases},
        separators=(",", ":"),
    )


def mint_case_id(when: datetime | None = None) -> str:
    when = when or datetime.now(timezone.utc)
    return when.strftime("CASE-%Y%m%d-%H%M%S")


def create_case(
    db_path: str | Path,
    cfg: dict,
    *,
    case_id: str | None = None,
    threshold: float | None = None,
    model_version: str = "unfitted",
) -> dict:
    cid = case_id or mint_case_id()
    thr = float(
        threshold
        if threshold is not None
        else (cfg.get("fusion") or {}).get("confidence_threshold", 0.83)
    )
    created = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    chash = config_hash(cfg)
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        snap = corpus_snapshot(conn)
        conn.execute(
            """
            INSERT INTO cases (
              case_id, created_at, corpus_snapshot, config_hash,
              model_version, threshold, status
            ) VALUES (?, ?, ?, ?, ?, ?, 'created')
            """,
            (cid, created, snap, chash, model_version, thr),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM cases WHERE case_id = ?", (cid,)).fetchone()
    return dict(row)


def set_status(db_path: str | Path, case_id: str, status: str, **fields) -> None:
    sets = ["status = ?"]
    vals: list = [status]
    for key in ("model_version", "threshold", "error", "report_path"):
        if key in fields:
            sets.append(f"{key} = ?")
            vals.append(fields[key])
    vals.append(case_id)
    with sqlite3.connect(db_path) as conn:
        conn.execute(f"UPDATE cases SET {', '.join(sets)} WHERE case_id = ?", vals)
        conn.commit()


def get_case(db_path: str | Path, case_id: str) -> dict | None:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM cases WHERE case_id = ?", (case_id,)).fetchone()
    return dict(row) if row else None
