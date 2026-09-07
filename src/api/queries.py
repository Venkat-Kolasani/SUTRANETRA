"""Read helpers shared by the FastAPI wrapper. No scoring."""

from __future__ import annotations

import json
import sqlite3
import tempfile
from pathlib import Path
from typing import Any

from src.explain.reason import explain_pair
from src.explain.trail import build_evidence_trail
from src.export.writers import (
    cluster_member_rows,
    cluster_subgraph,
    list_case_clusters,
    pair_shared_detail,
    search_corpus,
    shared_evidence_with_lineage,
)
from src.graph.build import render_pyvis
from src.llm.polish import polish_explanation
from src.opsec.scanner import list_findings
from src.pipeline.case import get_case

DEMO_PAIR = ("NW Nugz", "nw nugz")
_CLUSTER_HTML_CACHE: dict[tuple[str, int, float, int], str] = {}


def json_safe(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [json_safe(v) for v in obj]
    if isinstance(obj, bytes):
        return obj.hex()
    return obj


def open_db(db_path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path), timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def list_cases(conn: sqlite3.Connection) -> list[dict]:
    return [dict(r) for r in conn.execute("SELECT * FROM cases ORDER BY created_at DESC")]


def alias_options(conn: sqlite3.Connection, case_id: str) -> list[dict]:
    rows = list(
        conn.execute(
            """
            SELECT DISTINCT a.id, a.market, a.alias
            FROM clusters c
            JOIN aliases a ON a.id = c.alias_id
            WHERE c.case_id = ?
            ORDER BY a.market, a.alias
            """,
            (case_id,),
        )
    )
    seen = {r["id"] for r in rows}
    extra = conn.execute(
        """
        SELECT id, market, alias FROM aliases
        WHERE alias IN (?, ?)
        ORDER BY market, alias
        """,
        DEMO_PAIR,
    )
    for r in extra:
        if r["id"] not in seen:
            rows.append(r)
            seen.add(r["id"])
    return [{"label": f"{r['market']}:{r['alias']}", "alias_id": r["id"]} for r in rows]


def cluster_payload(conn: sqlite3.Connection, case_id: str, cluster_id: int, threshold: float) -> dict:
    members = cluster_member_rows(conn, case_id, cluster_id)
    alias_ids = [m["alias_id"] for m in members]
    shared = shared_evidence_with_lineage(conn, alias_ids) if alias_ids else []
    html = ""
    if members:
        revision = int(conn.execute("PRAGMA data_version").fetchone()[0])
        cache_key = (case_id, cluster_id, threshold, revision)
        html = _CLUSTER_HTML_CACHE.get(cache_key, "")
        if not html:
            sub = cluster_subgraph(conn, case_id, cluster_id, threshold)
            with tempfile.TemporaryDirectory() as tmpdir:
                path = Path(tmpdir) / "cluster.html"
                render_pyvis(sub, path, height="480px")
                html = path.read_text(encoding="utf-8")
            _CLUSTER_HTML_CACHE[cache_key] = html
            if len(_CLUSTER_HTML_CACHE) > 12:
                _CLUSTER_HTML_CACHE.pop(next(iter(_CLUSTER_HTML_CACHE)))
    return {"members": members, "shared": shared, "graph_html": html}


def pair_payload(
    conn: sqlite3.Connection,
    case_id: str,
    a_id: int,
    b_id: int,
    cfg: dict | None,
    *,
    polish: bool,
) -> dict:
    ev = explain_pair(conn, case_id, a_id, b_id)
    sentence = ev.get("template_sentence") or ""
    if polish:
        sentence = polish_explanation(ev, cfg)
    score = conn.execute(
        """
        SELECT s_char, s_embed, s_hard, s_time, confidence FROM pair_scores
        WHERE case_id = ?
          AND ((a_alias_id = ? AND b_alias_id = ?) OR (a_alias_id = ? AND b_alias_id = ?))
        """,
        (case_id, a_id, b_id, b_id, a_id),
    ).fetchone()
    return {
        "explanation": ev,
        "sentence": sentence,
        "polished": polish and sentence != ev.get("template_sentence"),
        "scores": dict(score) if score else None,
        "detail": pair_shared_detail(conn, a_id, b_id),
    }


def trail_payload(
    conn: sqlite3.Connection,
    case_id: str,
    *,
    cluster_id: int | None = None,
    a_alias_id: int | None = None,
    b_alias_id: int | None = None,
) -> list[dict]:
    return build_evidence_trail(
        conn,
        case_id,
        cluster_id=cluster_id,
        a_alias_id=a_alias_id,
        b_alias_id=b_alias_id,
    )


def search_payload(conn: sqlite3.Connection, query: str) -> list[dict]:
    return search_corpus(conn, query)


def case_row(db_path: str | Path, case_id: str) -> dict | None:
    row = get_case(db_path, case_id)
    if row is None:
        return None
    if isinstance(row.get("corpus_snapshot"), str):
        try:
            row = dict(row)
            row["corpus_snapshot"] = json.loads(row["corpus_snapshot"])
        except json.JSONDecodeError:
            pass
    return row


def opsec_payload(db_path: str | Path, case_id: str) -> list[dict]:
    return list_findings(db_path, case_id)


def clusters_payload(conn: sqlite3.Connection, case_id: str) -> list[dict]:
    return list_case_clusters(conn, case_id)
