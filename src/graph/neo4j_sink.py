"""Project the finished networkx graph into Neo4j (SPEC.md §13.1).

networkx remains the compute engine. This module only MERGEs already-scored
nodes and edges. Attribution never reads back from Neo4j.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

EVIDENCE_KINDS = ("pgp_fpr", "btc", "onion", "clearnet", "email")
BATCH = 5000
WRITE_RE = re.compile(
    r"\b(CREATE|MERGE|DELETE|DETACH|SET|DROP|REMOVE|LOAD\s+CSV|CALL\s+\{\s*CREATE)\b",
    re.IGNORECASE,
)

# Rehearsed stage queries (SPEC.md §13.1). Bind params only on shortest-path.
Q_THREE_MARKETS = """
MATCH (a:Alias)-[:MEMBER_OF]->(act:Actor)
WITH act, collect(DISTINCT a.market) AS mkts
WHERE size(mkts) >= 3
RETURN act.cluster_id AS cluster_id, mkts, act.max_confidence AS max_confidence
ORDER BY act.max_confidence DESC
"""
Q_SHORTEST = """
MATCH p = shortestPath(
  (a:Alias {name:$a, market:$a_market})-[:USED|LINKED_TO*..6]-(b:Alias {name:$b, market:$b_market})
)
RETURN [n IN nodes(p) | CASE
  WHEN n:Alias THEN n.market + ':' + n.name
  WHEN n:Evidence THEN n.kind + ':' + n.value
  WHEN n:Domain THEN 'domain:' + n.name
  WHEN n:Actor THEN 'actor:' + toString(n.cluster_id)
  ELSE labels(n)[0]
END] AS hops, length(p) AS len
"""
Q_SHARED_BTC = """
MATCH (e:Evidence {kind:'btc'})<-[:USED]-(a:Alias)
WITH e, count(DISTINCT a) AS n WHERE n > 1
RETURN e.value AS value, n ORDER BY n DESC LIMIT 20
"""
Q_CLEARNET_PIVOT = """
MATCH (a:Alias)-[:USED]->(e:Evidence {kind:'clearnet'})-[:PIVOTS_TO]->(d:Domain)
RETURN a.name AS name, a.market AS market, e.value AS clearnet, collect(d.name) AS siblings
"""


def active_profile(cfg: dict, profile: str | None = None) -> tuple[str, dict]:
    name = (
        profile
        or os.environ.get("SUTRANETRA_PROFILE")
        or cfg.get("profile")
        or "dev"
    )
    block = (cfg.get("profiles") or {}).get(name)
    if not block:
        raise SystemExit(f"unknown profile {name!r}")
    return name, block


def neo4j_settings(profile_block: dict) -> dict:
    n = dict(profile_block.get("neo4j") or {})
    n["password"] = os.environ.get("NEO4J_PASSWORD") or n.get("password") or ""
    n["reader_password"] = (
        os.environ.get("NEO4J_READER_PASSWORD") or n.get("reader_password") or ""
    )
    return n


def assert_readonly_cypher(cypher: str) -> None:
    """Courtesy regex — Prompt 15's agent tool uses this. Not a substitute for RBAC."""
    if WRITE_RE.search(cypher or ""):
        raise ValueError("write Cypher rejected")


def _host(value: str) -> str:
    raw = (value or "").strip().lower()
    if "://" in raw:
        host = (urlparse(raw).hostname or "").lower()
        return host[4:] if host.startswith("www.") else host
    host = raw.split("/")[0].split(":")[0]
    return host[4:] if host.startswith("www.") else host


def _driver(settings: dict):
    from neo4j import GraphDatabase

    pw = settings.get("password") or ""
    if not pw:
        raise SystemExit("Neo4j password empty — set NEO4J_PASSWORD")
    return GraphDatabase.driver(
        settings.get("uri") or "bolt://localhost:7687",
        auth=(settings.get("user") or "neo4j", pw),
    )


def _unwind(session, cypher: str, rows: list[dict], batch: int = BATCH) -> None:
    for i in range(0, len(rows), batch):
        session.run(cypher, rows=rows[i : i + batch])


def ensure_constraints(session) -> list[str]:
    session.run(
        "CREATE CONSTRAINT alias_market_name IF NOT EXISTS "
        "FOR (a:Alias) REQUIRE (a.market, a.name) IS UNIQUE"
    )
    session.run(
        "CREATE CONSTRAINT evidence_kind_value IF NOT EXISTS "
        "FOR (e:Evidence) REQUIRE (e.kind, e.value) IS UNIQUE"
    )
    session.run(
        "CREATE CONSTRAINT actor_cluster_id IF NOT EXISTS "
        "FOR (a:Actor) REQUIRE a.cluster_id IS UNIQUE"
    )
    session.run(
        "CREATE CONSTRAINT domain_name IF NOT EXISTS "
        "FOR (d:Domain) REQUIRE d.name IS UNIQUE"
    )
    recs = session.run("SHOW CONSTRAINTS YIELD name, type, labelsOrTypes, properties RETURN *")
    return [dict(r) for r in recs]


def _alias_rows(conn: sqlite3.Connection, case_id: str, bet: dict[str, float]) -> list[dict]:
    from src.graph.build import node_key

    out = []
    for r in conn.execute(
        """
        SELECT a.id, a.alias, a.market, a.n_posts, a.first_seen, a.last_seen, a.is_vendor,
               c.cluster_id
        FROM clusters c
        JOIN aliases a ON a.id = c.alias_id
        WHERE c.case_id = ?
        """,
        (case_id,),
    ):
        key = node_key(r["market"], r["alias"])
        out.append(
            {
                "name": r["alias"],
                "market": r["market"],
                "n_posts": int(r["n_posts"] or 0),
                "first_seen": r["first_seen"],
                "last_seen": r["last_seen"],
                "is_vendor": bool(r["is_vendor"]),
                "centrality": float(bet.get(key, 0.0)),
                "cluster_id": int(r["cluster_id"]),
            }
        )
    return out


def _actor_rows(conn: sqlite3.Connection, case_id: str) -> list[dict]:
    rows = []
    for r in conn.execute(
        """
        SELECT c.cluster_id,
               COUNT(*) AS n_aliases,
               MAX(c.confidence) AS max_confidence,
               GROUP_CONCAT(DISTINCT a.market) AS markets
        FROM clusters c
        JOIN aliases a ON a.id = c.alias_id
        WHERE c.case_id = ?
        GROUP BY c.cluster_id
        """,
        (case_id,),
    ):
        mkts = sorted({m for m in (r["markets"] or "").split(",") if m})
        rows.append(
            {
                "cluster_id": int(r["cluster_id"]),
                "n_aliases": int(r["n_aliases"]),
                "markets": mkts,
                "max_confidence": float(r["max_confidence"] or 0.0),
            }
        )
    return rows


def _link_rows(conn: sqlite3.Connection, case_id: str, threshold: float) -> list[dict]:
    rows = []
    for r in conn.execute(
        """
        SELECT p.confidence, p.s_char, p.s_embed, p.s_hard, p.s_time,
               aa.market AS a_market, aa.alias AS a_name,
               ab.market AS b_market, ab.alias AS b_name
        FROM pair_scores p
        JOIN aliases aa ON aa.id = p.a_alias_id
        JOIN aliases ab ON ab.id = p.b_alias_id
        JOIN clusters ca ON ca.case_id = p.case_id AND ca.alias_id = p.a_alias_id
        JOIN clusters cb ON cb.case_id = p.case_id AND cb.alias_id = p.b_alias_id
        WHERE p.case_id = ? AND p.confidence >= ?
        """,
        (case_id, threshold),
    ):
        if r["a_market"] == r["b_market"] and r["a_name"] == r["b_name"]:
            continue
        rows.append(
            {
                "a_market": r["a_market"],
                "a_name": r["a_name"],
                "b_market": r["b_market"],
                "b_name": r["b_name"],
                "confidence": float(r["confidence"]),
                "s_char": r["s_char"],
                "s_embed": r["s_embed"],
                "s_hard": r["s_hard"],
                "s_time": r["s_time"],
                "cross_market": bool(r["a_market"] != r["b_market"]),
            }
        )
    return rows


def _used_rows(conn: sqlite3.Connection, case_id: str, *, clustered_only: bool = True) -> list[dict]:
    kinds = ",".join("?" * len(EVIDENCE_KINDS))
    join_c = "JOIN clusters c ON c.alias_id = a.id AND c.case_id = ?" if clustered_only else ""
    params: tuple = (case_id, *EVIDENCE_KINDS) if clustered_only else EVIDENCE_KINDS
    q = f"""
        SELECT a.market, a.alias AS name, e.kind, e.value,
               COUNT(DISTINCT e.post_id) AS n_posts,
               MIN(p.ts) AS first_seen
        FROM evidence e
        JOIN aliases a ON a.id = e.alias_id
        {join_c}
        LEFT JOIN posts p ON p.id = e.post_id
        WHERE e.kind IN ({kinds})
        GROUP BY a.market, a.alias, e.kind, e.value
    """
    return [
        {
            "market": r["market"],
            "name": r["name"],
            "kind": r["kind"],
            "value": r["value"],
            "n_posts": int(r["n_posts"] or 0),
            "first_seen": r["first_seen"],
        }
        for r in conn.execute(q, params)
    ]


def _ct_seeds(conn: sqlite3.Connection, case_id: str) -> list[dict]:
    out = []
    for r in conn.execute(
        """
        SELECT value, detail FROM opsec_findings
        WHERE case_id = ? AND finding_kind = 'ct_sibling'
        """,
        (case_id,),
    ):
        try:
            detail = json.loads(r["detail"] or "{}")
        except json.JSONDecodeError:
            detail = {}
        seed = _host(detail.get("seed") or "")
        sib = _host(r["value"])
        if sib:
            out.append({"seed": seed, "domain": sib, "source": detail.get("source") or "ct"})
    return out


def _used_matching_ct(conn: sqlite3.Connection, case_id: str, seeds: list[dict]) -> list[dict]:
    """CT walk uses clustered aliases (and clustered corpus_clearnet). Do not fan out to the whole corpus."""
    extra = []
    extra.extend(_corpus_clearnet_used(conn, case_id))
    hosts = {s["seed"] for s in seeds if s.get("seed")}
    for r in conn.execute(
        """
        SELECT value FROM opsec_findings
        WHERE case_id = ? AND finding_kind IN ('clearnet_ref', 'tls_san')
        """,
        (case_id,),
    ):
        h = _host(r["value"])
        if h:
            hosts.add(h)
    if not hosts:
        return extra
    for u in _used_rows(conn, case_id, clustered_only=True):
        if u["kind"] not in ("clearnet", "onion"):
            continue
        h = _host(u["value"])
        if h in hosts or any(h.endswith("." + s) or s.endswith("." + h) for s in hosts if h):
            extra.append(u)
    return extra


def _corpus_clearnet_used(conn: sqlite3.Connection, case_id: str) -> list[dict]:
    """OpSec corpus hits are not always in `evidence`; still need USED for the CT walk."""
    extra = []
    for r in conn.execute(
        """
        SELECT value, detail FROM opsec_findings
        WHERE case_id = ? AND finding_kind = 'corpus_clearnet'
        """,
        (case_id,),
    ):
        try:
            detail = json.loads(r["detail"] or "{}")
        except json.JSONDecodeError:
            continue
        market, alias = detail.get("market"), detail.get("alias")
        if not market or not alias:
            continue
        in_graph = conn.execute(
            """
            SELECT 1 FROM clusters c JOIN aliases a ON a.id = c.alias_id
            WHERE c.case_id = ? AND a.market = ? AND a.alias = ?
            """,
            (case_id, market, alias),
        ).fetchone()
        if not in_graph:
            continue
        extra.append(
            {
                "market": market,
                "name": alias,
                "kind": "clearnet",
                "value": r["value"],
                "n_posts": 1,
                "first_seen": None,
            }
        )
    return extra


def _pivot_rows(conn: sqlite3.Connection, case_id: str, used: list[dict]) -> list[dict]:
    siblings = []
    for r in conn.execute(
        """
        SELECT value, detail FROM opsec_findings
        WHERE case_id = ? AND finding_kind = 'ct_sibling'
        """,
        (case_id,),
    ):
        try:
            detail = json.loads(r["detail"] or "{}")
        except json.JSONDecodeError:
            detail = {}
        seed = _host(detail.get("seed") or "")
        source = detail.get("source") or "ct"
        sib = _host(r["value"])
        if sib:
            siblings.append({"seed": seed, "domain": sib, "source": source})

    # Demo plant: scanner clearnet_ref erowid.org → CT sibling archive.erowid.org
    for r in conn.execute(
        """
        SELECT value FROM opsec_findings
        WHERE case_id = ? AND finding_kind IN ('clearnet_ref', 'tls_san', 'corpus_clearnet')
        """,
        (case_id,),
    ):
        host = _host(r["value"])
        if host and not any(s["seed"] == host for s in siblings):
            # keep seed so PIVOTS_TO can attach if a sibling shares the registrable name
            pass

    evidence_hosts: list[tuple[str, str]] = []
    seen_ev = set()
    for u in used:
        if u["kind"] not in ("clearnet", "onion"):
            continue
        h = _host(u["value"]) or u["value"]
        key = (u["kind"], u["value"])
        if key in seen_ev:
            continue
        seen_ev.add(key)
        evidence_hosts.append((u["kind"], u["value"], h))

    out = []
    seen = set()
    for kind, value, host in evidence_hosts:
        for s in siblings:
            seed = s["seed"]
            if not seed:
                continue
            if host == seed or host.endswith("." + seed) or seed.endswith("." + host) or seed in (host or ""):
                key = (kind, value, s["domain"])
                if key in seen:
                    continue
                seen.add(key)
                out.append(
                    {
                        "kind": kind,
                        "value": value,
                        "domain": s["domain"],
                        "source": s["source"],
                    }
                )
    return out


def project(
    db_path: str | Path,
    case_id: str,
    settings: dict,
    *,
    g=None,
    bet: dict[str, float] | None = None,
) -> dict[str, Any]:
    from src.graph.build import centralities, load_graph
    from src.pipeline.case import get_case

    case = get_case(db_path, case_id)
    if case is None:
        raise SystemExit(f"unknown case {case_id}")
    threshold = float(case["threshold"])
    t0 = time.perf_counter()
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        if g is None:
            g = load_graph(conn, case_id, threshold)
        if bet is None:
            _, bet = centralities(g)
        aliases = _alias_rows(conn, case_id, bet)
        actors = _actor_rows(conn, case_id)
        links = _link_rows(conn, case_id, threshold)
        used = _used_rows(conn, case_id)
        used.extend(_corpus_clearnet_used(conn, case_id))
        seeds = _ct_seeds(conn, case_id)
        used.extend(_used_matching_ct(conn, case_id, seeds))
        seen_used = set()
        deduped = []
        for u in used:
            key = (u["market"], u["name"], u["kind"], u["value"])
            if key in seen_used:
                continue
            seen_used.add(key)
            deduped.append(u)
        used = deduped
        have = {(a["market"], a["name"]) for a in aliases}
        for u in used:
            key = (u["market"], u["name"])
            if key in have:
                continue
            have.add(key)
            aliases.append(
                {
                    "name": u["name"],
                    "market": u["market"],
                    "n_posts": u.get("n_posts") or 0,
                    "first_seen": u.get("first_seen"),
                    "last_seen": None,
                    "is_vendor": False,
                    "centrality": 0.0,
                    "cluster_id": None,
                }
            )
        # clustered_only USED should not add stubs; keep the hook if corpus_clearnet names a clustered alias only.
        pivots = _pivot_rows(conn, case_id, used)

    driver = _driver(settings)
    database = settings.get("database") or "neo4j"
    try:
        with driver.session(database=database) as session:
            constraints = ensure_constraints(session)
            _unwind(
                session,
                """
                UNWIND $rows AS row
                MERGE (a:Alias {market: row.market, name: row.name})
                SET a.n_posts = row.n_posts,
                    a.first_seen = row.first_seen,
                    a.last_seen = row.last_seen,
                    a.is_vendor = row.is_vendor,
                    a.centrality = row.centrality
                """,
                aliases,
            )
            _unwind(
                session,
                """
                UNWIND $rows AS row
                MERGE (act:Actor {cluster_id: row.cluster_id})
                SET act.n_aliases = row.n_aliases,
                    act.markets = row.markets,
                    act.max_confidence = row.max_confidence
                """,
                actors,
            )
            _unwind(
                session,
                """
                UNWIND $rows AS row
                MATCH (a:Alias {market: row.market, name: row.name})
                MATCH (act:Actor {cluster_id: row.cluster_id})
                MERGE (a)-[:MEMBER_OF]->(act)
                """,
                [a for a in aliases if a.get("cluster_id") is not None],
            )
            _unwind(
                session,
                """
                UNWIND $rows AS row
                MATCH (a:Alias {market: row.a_market, name: row.a_name})
                MATCH (b:Alias {market: row.b_market, name: row.b_name})
                MERGE (a)-[r:LINKED_TO]->(b)
                SET r.confidence = row.confidence,
                    r.s_char = row.s_char,
                    r.s_embed = row.s_embed,
                    r.s_hard = row.s_hard,
                    r.s_time = row.s_time,
                    r.cross_market = row.cross_market
                """,
                links,
            )
            _unwind(
                session,
                """
                UNWIND $rows AS row
                MERGE (e:Evidence {kind: row.kind, value: row.value})
                WITH e, row
                MATCH (a:Alias {market: row.market, name: row.name})
                MERGE (a)-[u:USED]->(e)
                SET u.n_posts = row.n_posts, u.first_seen = row.first_seen
                """,
                used,
            )
            _unwind(
                session,
                """
                UNWIND $rows AS row
                MERGE (e:Evidence {kind: row.kind, value: row.value})
                MERGE (d:Domain {name: row.domain})
                SET d.source = row.source
                MERGE (e)-[:PIVOTS_TO]->(d)
                """,
                pivots,
            )
            counts = session.run(
                """
                MATCH (n:Alias) WITH count(n) AS aliases
                MATCH (a:Actor) WITH aliases, count(a) AS actors
                MATCH (e:Evidence) WITH aliases, actors, count(e) AS evidence
                MATCH (d:Domain) WITH aliases, actors, evidence, count(d) AS domains
                MATCH ()-[r:LINKED_TO]->() WITH aliases, actors, evidence, domains, count(r) AS linked
                MATCH ()-[u:USED]->() WITH aliases, actors, evidence, domains, linked, count(u) AS used
                MATCH ()-[p:PIVOTS_TO]->()
                RETURN aliases, actors, evidence, domains, linked, used, count(p) AS pivots
                """
            ).single()
    finally:
        driver.close()
    elapsed = time.perf_counter() - t0
    return {
        "case_id": case_id,
        "elapsed_s": round(elapsed, 3),
        "n_alias": len(aliases),
        "n_actor": len(actors),
        "n_linked": len(links),
        "n_used": len(used),
        "n_pivots": len(pivots),
        "constraints": constraints,
        "graph_counts": dict(counts) if counts else {},
    }


def counts(settings: dict) -> dict:
    driver = _driver(settings)
    try:
        with driver.session(database=settings.get("database") or "neo4j") as session:
            rec = session.run(
                """
                MATCH (n:Alias) WITH count(n) AS aliases
                MATCH (a:Actor) WITH aliases, count(a) AS actors
                MATCH (e:Evidence) WITH aliases, actors, count(e) AS evidence
                MATCH (d:Domain) WITH aliases, actors, evidence, count(d) AS domains
                MATCH ()-[r:LINKED_TO]->() WITH aliases, actors, evidence, domains, count(r) AS linked
                MATCH ()-[u:USED]->() WITH aliases, actors, evidence, domains, linked, count(u) AS used
                MATCH ()-[p:PIVOTS_TO]->()
                RETURN aliases, actors, evidence, domains, linked, used, count(p) AS pivots
                """
            ).single()
            return dict(rec) if rec else {}
    finally:
        driver.close()


def run_cypher(settings: dict, cypher: str, params: dict | None = None, *, readonly: bool = False) -> list[dict]:
    if readonly:
        assert_readonly_cypher(cypher)
    driver = _driver(settings)
    try:
        with driver.session(database=settings.get("database") or "neo4j") as session:
            result = session.run(cypher, params or {})
            return [dict(r) for r in result]
    finally:
        driver.close()


def rehearse(settings: dict, a: str, b: str, a_market: str, b_market: str) -> dict:
    return {
        "three_markets": run_cypher(settings, Q_THREE_MARKETS, readonly=True),
        "shortest": run_cypher(
            settings,
            Q_SHORTEST,
            {"a": a, "b": b, "a_market": a_market, "b_market": b_market},
            readonly=True,
        ),
        "shared_btc": run_cypher(settings, Q_SHARED_BTC, readonly=True),
        "clearnet_pivot": run_cypher(settings, Q_CLEARNET_PIVOT, readonly=True),
    }


def list_constraints(settings: dict) -> list[dict]:
    driver = _driver(settings)
    try:
        with driver.session(database=settings.get("database") or "neo4j") as session:
            return [
                dict(r)
                for r in session.run(
                    "SHOW CONSTRAINTS YIELD name, type, labelsOrTypes, properties RETURN *"
                )
            ]
    finally:
        driver.close()


def try_create_reader(settings: dict, reader_user: str, reader_password: str) -> dict:
    """Probe Community Edition RBAC. Never claim enforcement we did not observe."""
    driver = _driver(settings)
    out: dict[str, Any] = {"user": reader_user, "created": False, "role_granted": False, "notes": []}
    try:
        with driver.session(database="system") as session:
            try:
                session.run(
                    f"CREATE USER {reader_user} IF NOT EXISTS SET PASSWORD $pw CHANGE NOT REQUIRED",
                    pw=reader_password,
                )
                out["created"] = True
                out["notes"].append("CREATE USER succeeded (native auth available)")
            except Exception as e:
                out["notes"].append(f"CREATE USER failed: {e}")
                return out
            try:
                session.run(f"GRANT ROLE reader TO {reader_user}")
                out["role_granted"] = True
                out["notes"].append("GRANT ROLE reader succeeded")
            except Exception as e:
                out["notes"].append(f"GRANT ROLE reader failed: {e}")
    finally:
        driver.close()
    return out


def verify_reader_cannot_write(uri: str, user: str, password: str, database: str = "neo4j") -> dict:
    from neo4j import GraphDatabase

    out = {"connected": False, "write_rejected": False, "error": None}
    try:
        driver = GraphDatabase.driver(uri, auth=(user, password))
        try:
            with driver.session(database=database) as session:
                session.run("MATCH (n:Alias) RETURN count(n) AS n LIMIT 1").single()
                out["connected"] = True
                try:
                    session.run("CREATE (x:RbacProbe {k: 1})")
                    session.run("MATCH (x:RbacProbe) DETACH DELETE x")
                    out["write_rejected"] = False
                    out["error"] = "reader was allowed to CREATE (no enforced RO role)"
                except Exception as e:
                    out["write_rejected"] = True
                    out["error"] = str(e)
        finally:
            driver.close()
    except Exception as e:
        out["error"] = str(e)
    return out


def main(argv: list[str] | None = None) -> int:
    import argparse

    import yaml

    p = argparse.ArgumentParser(description="Project finished graph into Neo4j")
    p.add_argument("--config", default="config.yaml")
    p.add_argument("--db", default=None)
    p.add_argument("--case-id", required=True)
    p.add_argument("--profile", default=None)
    p.add_argument("--no-neo4j", action="store_true")
    p.add_argument("--rehearse", action="store_true")
    p.add_argument("--alias-a", default="nihilist23")
    p.add_argument("--alias-b", default="nxxxxxxx23")
    p.add_argument("--market-a", default="silkroad2")
    p.add_argument("--market-b", default="thehub")
    args = p.parse_args(argv)
    with open(args.config, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    name, block = active_profile(cfg, args.profile)
    settings = neo4j_settings(block)
    print(f"profile: {name}")
    print(f"neo4j.enabled: {bool(settings.get('enabled'))}")
    if args.no_neo4j or not settings.get("enabled"):
        print("neo4j: skipped")
        return 0
    db = args.db or cfg["paths"]["sqlite_db"]
    summary = project(db, args.case_id, settings)
    print("neo4j_sink")
    for k, v in summary.items():
        if k == "constraints":
            print(f"  constraints: {len(v)}")
            continue
        print(f"  {k}: {v}")
    if args.rehearse:
        print("rehearse")
        print(json.dumps(rehearse(settings, args.alias_a, args.alias_b, args.market_a, args.market_b), indent=2, default=str)[:12000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
