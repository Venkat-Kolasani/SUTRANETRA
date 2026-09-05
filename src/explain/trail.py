"""Ordered Evidence Trail (SPEC.md §15). Deterministic; never invents steps."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import networkx as nx

from src.evidence.score import WEIGHT
from src.explain.reason import _open, shorten
from src.graph.build import centralities, node_key

LINEAGE = ("source_archive", "scrape_date", "source_member_path", "content_sha256")
_CLEARNET_KINDS = frozenset({"clearnet_ref", "corpus_clearnet", "tls_san"})
_KIND_LABEL = {
    "pgp_fpr": "PGP fingerprint",
    "btc": "Shared BTC address",
    "xmr": "Shared XMR address",
    "onion": "onion address",
    "clearnet": "clearnet domain",
    "email": "email",
}


def build_evidence_trail(
    db: sqlite3.Connection | str | Path,
    case_id: str,
    *,
    cluster_id: int | None = None,
    a_alias_id: int | None = None,
    b_alias_id: int | None = None,
) -> list[dict]:
    """Return ordered trail steps for UI / JSON / agent. No LLM."""
    conn, own = _open(db)
    try:
        a_id, b_id = _resolve_pair(conn, case_id, cluster_id, a_alias_id, b_alias_id)
        return _trail_for_pair(conn, case_id, a_id, b_id)
    finally:
        if own:
            conn.close()


def _resolve_pair(
    conn: sqlite3.Connection,
    case_id: str,
    cluster_id: int | None,
    a_alias_id: int | None,
    b_alias_id: int | None,
) -> tuple[int, int | None]:
    if a_alias_id is not None and b_alias_id is not None:
        return int(a_alias_id), int(b_alias_id)
    if cluster_id is None:
        raise ValueError("cluster_id or both alias ids required")
    members = [
        r["alias_id"]
        for r in conn.execute(
            """
            SELECT alias_id FROM clusters
            WHERE case_id = ? AND cluster_id = ?
            ORDER BY alias_id
            """,
            (case_id, cluster_id),
        )
    ]
    if not members:
        raise ValueError(f"empty cluster {cluster_id}")
    if len(members) == 1:
        return members[0], None
    ranked = _rank_cluster(conn, case_id, members)
    return _pair_among(conn, case_id, ranked)


def _rank_cluster(conn: sqlite3.Connection, case_id: str, members: list[int]) -> list[int]:
    case = conn.execute(
        "SELECT threshold FROM cases WHERE case_id = ?", (case_id,)
    ).fetchone()
    threshold = float(case["threshold"]) if case else 0.0
    q = ",".join("?" * len(members))
    rows = conn.execute(
        f"""
        SELECT p.a_alias_id, p.b_alias_id, p.confidence,
               aa.market AS a_market, aa.alias AS a_alias,
               ab.market AS b_market, ab.alias AS b_alias
        FROM pair_scores p
        JOIN aliases aa ON aa.id = p.a_alias_id
        JOIN aliases ab ON ab.id = p.b_alias_id
        WHERE p.case_id = ? AND p.confidence >= ?
          AND p.a_alias_id IN ({q}) AND p.b_alias_id IN ({q})
        """,
        (case_id, threshold, *members, *members),
    )
    g = nx.Graph()
    for r in rows:
        na, nb = node_key(r["a_market"], r["a_alias"]), node_key(r["b_market"], r["b_alias"])
        g.add_node(na, alias_id=r["a_alias_id"])
        g.add_node(nb, alias_id=r["b_alias_id"])
        g.add_edge(na, nb, weight=float(r["confidence"]))
    if g.number_of_nodes() == 0:
        return list(members)
    deg, bet = centralities(g)

    def key(n: str) -> tuple:
        return (bet.get(n, 0.0), deg.get(n, 0.0), -int(g.nodes[n]["alias_id"]))

    ordered = sorted(g.nodes(), key=key, reverse=True)
    return [g.nodes[n]["alias_id"] for n in ordered]


def _pair_among(
    conn: sqlite3.Connection, case_id: str, ranked: list[int]
) -> tuple[int, int]:
    top = ranked[:15]
    markets = {
        r["id"]: r["market"]
        for r in conn.execute(
            f"SELECT id, market FROM aliases WHERE id IN ({','.join('?' * len(top))})",
            top,
        )
    }
    best: tuple | None = None
    for i, a in enumerate(top):
        for b in top[i + 1 :]:
            r = conn.execute(
                """
                SELECT s_hard, confidence FROM pair_scores
                WHERE case_id = ?
                  AND ((a_alias_id = ? AND b_alias_id = ?)
                    OR (a_alias_id = ? AND b_alias_id = ?))
                """,
                (case_id, a, b, b, a),
            ).fetchone()
            if r is None:
                continue
            cross = int(markets.get(a) != markets.get(b))
            key = (float(r["s_hard"] or 0), cross, float(r["confidence"] or 0))
            if best is None or key > best[0]:
                best = (key, a, b)
    if best:
        return best[1], best[2]
    return ranked[0], ranked[1]


def _trail_for_pair(
    conn: sqlite3.Connection, case_id: str, a_id: int, b_id: int | None
) -> list[dict]:
    steps: list[dict] = []
    a = _alias_row(conn, a_id)
    steps.append(_alias_step(a))
    shared: list[dict] = []
    if b_id is not None:
        shared = _shared_with_posts(conn, a_id, b_id)
        if shared:
            top = shared[0]
            steps.append(_post_step(top["post_a"]))
            steps.append(_evidence_step(top))
        b = _alias_row(conn, b_id)
        steps.append(_alias_step(b))
        if shared:
            steps.append(_post_step(shared[0]["post_b"]))
            for item in shared[1:3]:
                steps.append(_evidence_step(item))
        score = _score_step(conn, case_id, a_id, b_id)
        if score:
            steps.append(score)
        steps.extend(_opsec_ct_steps(conn, case_id, a, b))
    return steps


def _alias_row(conn: sqlite3.Connection, alias_id: int) -> sqlite3.Row:
    r = conn.execute("SELECT * FROM aliases WHERE id = ?", (alias_id,)).fetchone()
    if r is None:
        raise ValueError(f"unknown alias {alias_id}")
    return r


def _alias_step(r: sqlite3.Row) -> dict:
    return {
        "type": "alias",
        "label": f"{r['alias']} ({r['market']})",
        "alias_id": r["id"],
        "alias": r["alias"],
        "market": r["market"],
        "n_posts": r["n_posts"],
    }


def _post_step(p: dict) -> dict:
    step = {
        "type": "post",
        "label": (
            f"Post #{p['post_id']}  ·  {p['source_archive']} / {p['scrape_date']} "
            f"/ {p['source_member_path']}"
        ),
        "post_id": p["post_id"],
        "evidence_id": p.get("evidence_id"),
    }
    for k in LINEAGE:
        step[k] = p[k]
    return step


def _evidence_step(item: dict) -> dict:
    kind, value = item["kind"], item["value"]
    lab = _KIND_LABEL.get(kind, kind)
    return {
        "type": "evidence",
        "label": f"{lab} {shorten(value, 10, 6)}",
        "kind": kind,
        "value": value,
        "evidence_ids": item["evidence_ids"],
        "post_ids": [item["post_a"]["post_id"], item["post_b"]["post_id"]],
    }


def _score_step(conn: sqlite3.Connection, case_id: str, a: int, b: int) -> dict | None:
    r = conn.execute(
        """
        SELECT * FROM pair_scores
        WHERE case_id = ?
          AND ((a_alias_id = ? AND b_alias_id = ?)
            OR (a_alias_id = ? AND b_alias_id = ?))
        """,
        (case_id, a, b, b, a),
    ).fetchone()
    if r is None or r["confidence"] is None:
        return None
    bits = []
    for name, key in (
        ("S_char", "s_char"),
        ("S_embed", "s_embed"),
        ("S_hard", "s_hard"),
        ("S_time", "s_time"),
    ):
        if r[key] is not None:
            bits.append(f"{name}={float(r[key]):.2f}")
    label = f"Fused confidence {float(r['confidence']):.2f}"
    if bits:
        label += "   (" + " / ".join(bits) + ")"
    return {
        "type": "score",
        "label": label,
        "case_id": case_id,
        "a_alias_id": a,
        "b_alias_id": b,
        "confidence": r["confidence"],
        "s_char": r["s_char"],
        "s_embed": r["s_embed"],
        "s_hard": r["s_hard"],
        "s_time": r["s_time"],
        "n_shared_hard": r["n_shared_hard"],
    }


def _shared_with_posts(conn: sqlite3.Connection, a: int, b: int) -> list[dict]:
    rows = conn.execute(
        """
        SELECT e.kind, e.value, GROUP_CONCAT(e.id) AS evidence_ids
        FROM evidence e
        WHERE e.alias_id IN (?, ?) AND e.post_id IS NOT NULL
        GROUP BY e.kind, e.value
        HAVING COUNT(DISTINCT e.alias_id) = 2
        """,
        (a, b),
    ).fetchall()
    out = []
    for r in rows:
        pa = _witness(conn, a, r["kind"], r["value"])
        pb = _witness(conn, b, r["kind"], r["value"])
        if pa is None or pb is None:
            continue
        ids = [int(x) for x in str(r["evidence_ids"]).split(",") if x]
        out.append(
            {
                "kind": r["kind"],
                "value": r["value"],
                "evidence_ids": ids,
                "post_a": pa,
                "post_b": pb,
            }
        )
    out.sort(key=lambda x: (-WEIGHT.get(x["kind"], 0.0), x["kind"], x["value"]))
    return out


def _witness(conn: sqlite3.Connection, alias_id: int, kind: str, value: str) -> dict | None:
    r = conn.execute(
        """
        SELECT e.id AS evidence_id, p.id AS post_id,
               p.source_archive, p.scrape_date, p.source_member_path, p.content_sha256
        FROM evidence e
        JOIN posts p ON p.id = e.post_id
        WHERE e.alias_id = ? AND e.kind = ? AND e.value = ?
        ORDER BY p.scrape_date DESC, p.id DESC
        LIMIT 1
        """,
        (alias_id, kind, value),
    ).fetchone()
    return dict(r) if r else None


def _norm_domain(value: str) -> str:
    v = value.lower().strip()
    for p in ("https://", "http://"):
        if v.startswith(p):
            v = v[len(p) :]
    return v.split("/")[0].split(":")[0].lstrip(".")


def _alias_clearnet(conn: sqlite3.Connection, alias_id: int) -> set[str]:
    return {
        _norm_domain(r["value"])
        for r in conn.execute(
            "SELECT value FROM evidence WHERE alias_id = ? AND kind = 'clearnet'",
            (alias_id,),
        )
    }


def _opsec_ct_steps(
    conn: sqlite3.Connection, case_id: str, a: sqlite3.Row, b: sqlite3.Row
) -> list[dict]:
    domains = _alias_clearnet(conn, a["id"]) | _alias_clearnet(conn, b["id"])
    names = {a["alias"], b["alias"]}
    findings = list(
        conn.execute(
            "SELECT * FROM opsec_findings WHERE case_id = ? ORDER BY id",
            (case_id,),
        )
    )
    opsec, certs, siblings = [], [], []
    seen: set[tuple[str, str]] = set()
    for f in findings:
        kind = f["finding_kind"]
        val = f["value"]
        detail = {}
        if f["detail"]:
            try:
                parsed = json.loads(f["detail"])
                if isinstance(parsed, dict):
                    detail = parsed
            except json.JSONDecodeError:
                detail = {}
        linked = False
        nv = _norm_domain(val)
        seed = _norm_domain(str(detail["seed"])) if detail.get("seed") else ""
        if kind in _CLEARNET_KINDS:
            if nv in domains:
                linked = True
            elif detail.get("alias") in names:
                linked = True
                domains.add(nv)
        elif kind in ("ct_sibling", "ct_cert"):
            linked = seed in domains or nv in domains
        if not linked:
            continue
        dedupe = (kind, nv or val)
        if dedupe in seen:
            continue
        seen.add(dedupe)
        row = dict(f)
        if kind in _CLEARNET_KINDS:
            opsec.append(row)
        elif kind == "ct_cert":
            certs.append(row)
        elif kind == "ct_sibling":
            siblings.append(row)
    steps = []
    for f in opsec:
        steps.append(
            {
                "type": "opsec",
                "label": f"Clearnet domain {f['value']}",
                "finding_id": f["id"],
                "finding_kind": f["finding_kind"],
                "value": f["value"],
            }
        )
    for f in certs:
        steps.append(
            {
                "type": "ct_cert",
                "label": f"CT certificate {shorten(f['value'], 12, 8)}",
                "finding_id": f["id"],
                "finding_kind": f["finding_kind"],
                "value": f["value"],
            }
        )
    for f in siblings:
        steps.append(
            {
                "type": "ct_domain",
                "label": f"Sibling domain {f['value']}",
                "finding_id": f["id"],
                "finding_kind": f["finding_kind"],
                "value": f["value"],
            }
        )
    return steps


def main(argv: list[str] | None = None) -> int:
    import argparse

    import yaml

    p = argparse.ArgumentParser(description="SUTRANETRA Evidence Trail")
    p.add_argument("--config", default="config.yaml")
    p.add_argument("--db", default=None)
    p.add_argument("--case-id", required=True)
    p.add_argument("--cluster-id", type=int, default=None)
    p.add_argument("--a", type=int, default=None)
    p.add_argument("--b", type=int, default=None)
    args = p.parse_args(argv)
    with open(args.config, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    db = args.db or cfg["paths"]["sqlite_db"]
    trail = build_evidence_trail(
        db, args.case_id, cluster_id=args.cluster_id, a_alias_id=args.a, b_alias_id=args.b
    )
    for i, s in enumerate(trail, 1):
        print(f"{i:02d}  {s['type']:10s}  {s['label']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
