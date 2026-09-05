"""Read-only investigator tools (SPEC.md §16.2). Thin wrappers; no scoring."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any
from urllib.parse import quote

from langchain_core.tools import BaseTool, tool

from src.export.writers import cluster_member_rows, list_case_clusters
from src.explain.trail import build_evidence_trail
from src.graph.build import shared_evidence_with_lineage
from src.graph.neo4j_sink import active_profile, assert_readonly_cypher, neo4j_settings, run_cypher
from src.opsec.ct_pivot import pivot as ct_pivot_fn
from src.opsec.scanner import scan_target, validate_scan_target
from src.temporal.activity import hour_histogram, parse_ts, timezone_estimate

TOOL_NAMES = (
    "search_evidence",
    "get_cluster",
    "score_pair",
    "evidence_trail",
    "get_case",
    "alias_timeline",
    "ct_pivot",
    "opsec_scan",
    "cypher_query",
)


def open_ro(db_path: str | Path) -> sqlite3.Connection:
    """SQLite URI mode=ro — writes fail at the connection, not by convention."""
    abs_path = Path(db_path).resolve().as_posix()
    uri = f"file:{quote(abs_path, safe='/')}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def reject_write_cypher(question_cypher: str) -> None:
    """Courtesy regex for cypher_query. Community Edition has no GRANT ROLE reader."""
    assert_readonly_cypher(question_cypher)


def _rows(seq) -> list[dict]:
    out = []
    for r in seq:
        d = dict(r)
        out.append({k: (v if not isinstance(v, bytes) else v.hex()) for k, v in d.items()})
    return out


def _alias_id(conn: sqlite3.Connection, market: str, alias: str) -> int:
    r = conn.execute(
        "SELECT id FROM aliases WHERE market = ? AND alias = ?",
        (market, alias),
    ).fetchone()
    if r is None:
        raise ValueError(f"unknown alias {market}:{alias}")
    return int(r["id"])


def _evidence_by_kind_value(conn: sqlite3.Connection, kind: str, value: str) -> list[dict]:
    return _rows(
        conn.execute(
            """
            SELECT e.id AS evidence_id, e.kind, e.value, e.alias_id,
                   a.market, a.alias, e.post_id, p.msg_id,
                   p.source_archive, p.scrape_date, p.source_member_path,
                   p.content_sha256
            FROM evidence e
            JOIN aliases a ON a.id = e.alias_id
            LEFT JOIN posts p ON p.id = e.post_id
            WHERE e.kind = ? AND (e.value = ? OR e.value LIKE ?)
            LIMIT 80
            """,
            (kind, value, f"%{value}%"),
        )
    )


def _holders(conn: sqlite3.Connection, kind: str, value: str, alias_ids: list[int]) -> list[dict]:
    qmarks = ",".join("?" * len(alias_ids))
    return _rows(
        conn.execute(
            f"""
            SELECT DISTINCT a.market, a.alias, a.id AS alias_id
            FROM evidence e JOIN aliases a ON a.id = e.alias_id
            WHERE e.kind = ? AND e.value = ? AND e.alias_id IN ({qmarks})
            ORDER BY a.market, a.alias
            """,
            [kind, value, *alias_ids],
        )
    )


def make_tools(db_path: str | Path, case_id: str, cfg: dict) -> list[BaseTool]:
    db_path = str(db_path)
    cache_dir = Path((cfg.get("paths") or {}).get("ct_cache") or "data/cache/ct")
    token = (cfg.get("opsec") or {}).get("certspotter_token")

    @tool
    def search_evidence(kind: str, value: str) -> dict:
        """Find every alias linked to a hard-evidence identifier.

        Use when the question names a wallet, PGP fingerprint, onion host, email,
        or clearnet domain. `kind` must be one of: pgp_fpr, btc, onion, clearnet, email.
        `value` should be the identifier. If the question only names a handle, pass
        that handle as `value` with kind=pgp_fpr (or btc/onion): the tool resolves
        that alias's identifiers and returns every alias that reused them.
        Returns a compact dict: n_aliases, aliases[{market,alias,alias_id}],
        and sample[] lineage rows (evidence_id, archive, sha256). Does not score.
        Answer using aliases[] only — do not invent handles.
        """
        conn = open_ro(db_path)
        try:
            rows = _evidence_by_kind_value(conn, kind, value)
            if not rows:
                seeds = conn.execute(
                    """
                    SELECT DISTINCT e.value FROM evidence e
                    JOIN aliases a ON a.id = e.alias_id
                    WHERE e.kind = ? AND a.alias = ?
                    LIMIT 8
                    """,
                    (kind, value),
                ).fetchall()
                seen: set[int] = set()
                rows = []
                for seed in seeds:
                    for row in _evidence_by_kind_value(conn, kind, seed["value"]):
                        eid = row.get("evidence_id")
                        if eid in seen:
                            continue
                        seen.add(eid)
                        rows.append(row)
                        if len(rows) >= 80:
                            break
                    if len(rows) >= 80:
                        break
            aliases, seen_a = [], set()
            for row in rows:
                key = (row.get("market"), row.get("alias"))
                if key in seen_a:
                    continue
                seen_a.add(key)
                aliases.append(
                    {
                        "market": row.get("market"),
                        "alias": row.get("alias"),
                        "alias_id": row.get("alias_id"),
                    }
                )
            return {
                "kind": kind,
                "value": value,
                "n_evidence_rows": len(rows),
                "n_aliases": len(aliases),
                "truncated": len(rows) >= 80,
                "aliases": aliases[:24],
                "sample": rows[:8],
            }
        finally:
            conn.close()

    @tool
    def get_cluster(alias: str, market: str) -> dict:
        """Return the case-scoped actor cluster that contains this alias.

        Use when asked which aliases cluster with a named handle, which markets
        it spans, or shared evidence inside that component. Looks up stored
        `clusters` for the active case — does not recompute components.
        """
        conn = open_ro(db_path)
        try:
            aid = _alias_id(conn, market, alias)
            row = conn.execute(
                """
                SELECT cluster_id, confidence FROM clusters
                WHERE case_id = ? AND alias_id = ?
                """,
                (case_id, aid),
            ).fetchone()
            if row is None:
                return {"case_id": case_id, "alias": alias, "market": market, "cluster_id": None}
            cid = int(row["cluster_id"])
            summaries = [s for s in list_case_clusters(conn, case_id) if s["cluster_id"] == cid]
            members = cluster_member_rows(conn, case_id, cid)
            aids = [m["alias_id"] for m in members]
            shared = shared_evidence_with_lineage(conn, aids)
            for item in shared:
                item["aliases"] = _holders(conn, item["kind"], item["value"], aids)
            return {
                "case_id": case_id,
                "cluster_id": cid,
                "query_alias": f"{market}:{alias}",
                "query_confidence": float(row["confidence"] or 0),
                "summary": summaries[0] if summaries else {},
                "members": members,
                "shared_evidence": shared,
            }
        finally:
            conn.close()

    @tool
    def score_pair(alias_a: str, market_a: str, alias_b: str, market_b: str) -> dict:
        """Return stored per-feature scores and fused confidence for one alias pair.

        Use when asked how similar two named aliases are, or for S_char / S_embed /
        S_hard / S_time / confidence. Reads `pair_scores` for the active case only.
        Never fits a model or invents a score.
        """
        conn = open_ro(db_path)
        try:
            a = _alias_id(conn, market_a, alias_a)
            b = _alias_id(conn, market_b, alias_b)
            row = conn.execute(
                """
                SELECT * FROM pair_scores
                WHERE case_id = ?
                  AND ((a_alias_id = ? AND b_alias_id = ?)
                    OR (a_alias_id = ? AND b_alias_id = ?))
                """,
                (case_id, a, b, b, a),
            ).fetchone()
            if row is None:
                return {
                    "case_id": case_id,
                    "pair": [f"{market_a}:{alias_a}", f"{market_b}:{alias_b}"],
                    "scored": False,
                }
            d = dict(row)
            d["scored"] = True
            d["pair"] = [f"{market_a}:{alias_a}", f"{market_b}:{alias_b}"]
            return d
        finally:
            conn.close()

    @tool
    def evidence_trail(
        cluster_id: int | None = None,
        alias_a: str | None = None,
        market_a: str | None = None,
        alias_b: str | None = None,
        market_b: str | None = None,
    ) -> list[dict]:
        """Return the ordered Evidence Trail for a cluster or a named pair.

        Use when asked to walk the evidence, show the trail, or explain how two
        aliases connect. Calls explain.trail.build_evidence_trail. Provide
        cluster_id, or both aliases with their markets. Steps include post lineage.
        """
        conn = open_ro(db_path)
        try:
            if cluster_id is not None:
                cluster_id = int(cluster_id)
            a_id = _alias_id(conn, market_a, alias_a) if alias_a and market_a else None
            b_id = _alias_id(conn, market_b, alias_b) if alias_b and market_b else None
            return build_evidence_trail(
                conn,
                case_id,
                cluster_id=cluster_id,
                a_alias_id=a_id,
                b_alias_id=b_id,
            )
        finally:
            conn.close()

    @tool
    def get_case() -> dict:
        """Return metadata for the active investigation case.

        Use for corpus snapshot, config hash, model version, threshold, and status.
        This is the ledger row that makes a run repeatable — not a verdict.
        """
        conn = open_ro(db_path)
        try:
            row = conn.execute("SELECT * FROM cases WHERE case_id = ?", (case_id,)).fetchone()
            return dict(row) if row else {"case_id": case_id, "missing": True}
        finally:
            conn.close()

    @tool
    def alias_timeline(alias: str, market: str) -> dict:
        """Posting activity over time, hour-of-day histogram, estimated UTC offset.

        Use for when an alias posted, activity hours, or timezone hypothesis.
        Offset is a weak evening-peak indicator, never a location claim.
        Prefers stored alias_activity; otherwise computes from posts in-memory
        without writing.
        """
        conn = open_ro(db_path)
        try:
            aid = _alias_id(conn, market, alias)
            try:
                stored = conn.execute(
                    "SELECT * FROM alias_activity WHERE alias_id = ?", (aid,)
                ).fetchone()
            except sqlite3.OperationalError:
                stored = None
            posts = _rows(
                conn.execute(
                    """
                    SELECT ts, msg_id, source_archive, scrape_date, source_member_path,
                           content_sha256
                    FROM posts WHERE market = ? AND alias = ? AND ts IS NOT NULL AND ts != ''
                    ORDER BY ts LIMIT 200
                    """,
                    (market, alias),
                )
            )
            out: dict[str, Any] = {
                "alias_id": aid,
                "alias": alias,
                "market": market,
                "n_posts_sampled": len(posts),
                "posts": posts[:40],
            }
            if stored:
                out["stored_activity"] = dict(stored)
                return out
            hours = []
            for p in posts:
                dt = parse_ts(p.get("ts"))
                if dt is not None:
                    hours.append(dt.hour)
            hist = hour_histogram(hours).tolist() if hours else []
            out["hour_hist"] = hist
            out["timezone"] = timezone_estimate(hours)
            return out
        finally:
            conn.close()

    @tool
    def ct_pivot(domain: str) -> dict:
        """Certificate Transparency pivot for a clearnet domain (cache-first, no live query).

        Use after search_evidence finds a clearnet leak, or when asked what other
        hostnames share a cert/public key with a domain. Returns siblings from
        data/cache/ct. Does not write SQLite. Pair with search_evidence in one turn
        for 'what else does this operator run?'.
        """
        conn = open_ro(db_path)
        try:
            return ct_pivot_fn(domain, cache_dir, live=False, token=token)
        finally:
            conn.close()

    @tool
    def opsec_scan(target_url: str) -> list[dict] | dict:
        """Scan the localhost demo target for planted misconfigurations.

        Use only for http://127.0.0.1 or localhost URLs. Rejects any other host.
        Returns scanner findings in memory — does not INSERT into opsec_findings.
        This is the only tool that makes outbound HTTP requests.
        """
        conn = open_ro(db_path)
        try:
            http = validate_scan_target(target_url)
            return scan_target(http, None)
        except ValueError as e:
            return {"error": str(e), "rejected": True, "target": target_url}
        finally:
            conn.close()

    @tool
    def cypher_query(question_cypher: str) -> list[dict] | dict:
        """Run a READ-ONLY Cypher query against the projected actor graph.

        Use for graph-shaped questions (shortest path, three-market actors, shared
        wallets) that no other tool covers. Rejects CREATE/MERGE/DELETE/SET/DROP.
        Community Edition cannot GRANT a read-only role — regex + execute_read
        are the controls; writer credentials stay in the pipeline sink.
        """
        conn = open_ro(db_path)
        try:
            reject_write_cypher(question_cypher)
            name, block = active_profile(cfg)
            settings = neo4j_settings(block)
            if not settings.get("enabled") and not settings.get("password"):
                # still try bolt if password is in the environment
                pass
            try:
                return run_cypher(settings, question_cypher, readonly=True)
            except Exception as e:
                return {
                    "error": str(e),
                    "profile": name,
                    "note": "Neo4j optional; use pyvis/exports if the server is down.",
                }
        finally:
            conn.close()

    return [
        search_evidence,
        get_cluster,
        score_pair,
        evidence_trail,
        get_case,
        alias_timeline,
        ct_pivot,
        opsec_scan,
        cypher_query,
    ]
