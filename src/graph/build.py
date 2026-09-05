"""Case-scoped actor graph (SPEC.md §13). networkx only — no Neo4j/LangGraph."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import networkx as nx

from src.pipeline.case import get_case

CROSS_EDGE = "#d35400"
SAME_EDGE = "#5d6d7e"
MARKET_COLOR = {
    "silkroad1": "#c9a227",
    "silkroad2": "#3d8bfd",
    "thehub": "#2ecc71",
    "nucleus": "#e67e22",
    "cannabisroad3": "#9b59b6",
}


def node_key(market: str, alias: str) -> str:
    return f"{market}:{alias}"


def load_graph(conn: sqlite3.Connection, case_id: str, threshold: float) -> nx.Graph:
    g = nx.Graph()
    rows = conn.execute(
        """
        SELECT p.a_alias_id, p.b_alias_id, p.confidence,
               aa.market AS a_market, aa.alias AS a_alias,
               ab.market AS b_market, ab.alias AS b_alias
        FROM pair_scores p
        JOIN aliases aa ON aa.id = p.a_alias_id
        JOIN aliases ab ON ab.id = p.b_alias_id
        WHERE p.case_id = ? AND p.confidence >= ?
        """,
        (case_id, threshold),
    )
    for r in rows:
        na = node_key(r["a_market"], r["a_alias"])
        nb = node_key(r["b_market"], r["b_alias"])
        if na == nb:
            continue
        g.add_node(
            na,
            alias_id=r["a_alias_id"],
            market=r["a_market"],
            alias=r["a_alias"],
        )
        g.add_node(
            nb,
            alias_id=r["b_alias_id"],
            market=r["b_market"],
            alias=r["b_alias"],
        )
        g.add_edge(
            na,
            nb,
            weight=float(r["confidence"]),
            cross_market=int(r["a_market"] != r["b_market"]),
        )
    return g


def cluster_components(g: nx.Graph) -> list[list[str]]:
    comps = [sorted(c) for c in nx.connected_components(g)]
    comps.sort(key=lambda c: (-len(c), c[0] if c else ""))
    return comps


def centralities(g: nx.Graph) -> tuple[dict[str, float], dict[str, float]]:
    if g.number_of_nodes() == 0:
        return {}, {}
    deg = nx.degree_centrality(g)
    # ponytail: exact betweenness is fine while the thresholded graph stays hundreds of nodes.
    bet = nx.betweenness_centrality(g, weight="weight", normalized=True)
    return deg, bet


def persist_clusters(
    conn: sqlite3.Connection,
    case_id: str,
    g: nx.Graph,
    comps: list[list[str]],
    deg: dict[str, float],
    bet: dict[str, float],
) -> None:
    conn.execute("DELETE FROM clusters WHERE case_id = ?", (case_id,))
    rows = []
    for cid, members in enumerate(comps, start=1):
        sub = g.subgraph(members)
        for n in members:
            inc = [d["weight"] for _, _, d in sub.edges(n, data=True)]
            conf = max(inc) if inc else 0.0
            rows.append(
                (
                    case_id,
                    cid,
                    g.nodes[n]["alias_id"],
                    conf,
                )
            )
    conn.executemany(
        """
        INSERT INTO clusters (case_id, cluster_id, alias_id, confidence)
        VALUES (?, ?, ?, ?)
        """,
        rows,
    )
    conn.commit()


def shared_evidence_with_lineage(
    conn: sqlite3.Connection, alias_ids: list[int]
) -> list[dict]:
    if len(alias_ids) < 2:
        return []
    qmarks = ",".join("?" * len(alias_ids))
    rows = conn.execute(
        f"""
        SELECT e.kind, e.value, COUNT(DISTINCT e.alias_id) AS n_aliases,
               MIN(p.source_archive) AS source_archive,
               MIN(p.scrape_date) AS scrape_date,
               MIN(p.source_member_path) AS source_member_path,
               MIN(p.content_sha256) AS content_sha256,
               MIN(p.market) AS post_market,
               MIN(p.msg_id) AS msg_id
        FROM evidence e
        JOIN posts p ON p.id = e.post_id
        WHERE e.alias_id IN ({qmarks}) AND e.post_id IS NOT NULL
        GROUP BY e.kind, e.value
        HAVING COUNT(DISTINCT e.alias_id) >= 2
        ORDER BY n_aliases DESC
        LIMIT 20
        """,
        alias_ids,
    )
    return [dict(r) for r in rows]


def cluster_report(
    conn: sqlite3.Connection,
    g: nx.Graph,
    members: list[str],
    cluster_id: int,
    deg: dict[str, float],
    bet: dict[str, float],
) -> dict:
    alias_ids = [g.nodes[n]["alias_id"] for n in members]
    qmarks = ",".join("?" * len(alias_ids))
    stats = conn.execute(
        f"""
        SELECT COUNT(*) AS n_posts, MIN(ts) AS first_ts, MAX(ts) AS last_ts
        FROM posts WHERE (market || ':' || alias) IN ({qmarks})
        """,
        members,
    ).fetchone()
    markets = sorted({g.nodes[n]["market"] for n in members})
    core = max(members, key=lambda n: (bet.get(n, 0.0), deg.get(n, 0.0)))
    return {
        "cluster_id": cluster_id,
        "n_members": len(members),
        "markets": markets,
        "n_markets": len(markets),
        "n_posts": stats["n_posts"],
        "first_ts": stats["first_ts"],
        "last_ts": stats["last_ts"],
        "core_alias": core,
        "members": [
            {
                "node": n,
                "alias_id": g.nodes[n]["alias_id"],
                "degree_centrality": deg.get(n, 0.0),
                "betweenness": bet.get(n, 0.0),
            }
            for n in members
        ],
        "shared_evidence": shared_evidence_with_lineage(conn, alias_ids),
    }


def render_pyvis(g: nx.Graph, path: Path, *, height: str = "800px") -> None:
    from pyvis.network import Network

    path.parent.mkdir(parents=True, exist_ok=True)
    if g.number_of_nodes() == 0:
        path.write_text("<html><body>empty graph</body></html>", encoding="utf-8")
        return
    pos = nx.spring_layout(g, seed=0, k=2 / max(g.number_of_nodes(), 1) ** 0.5)
    # in_line: Streamlit components.html is an iframe with no cwd ./lib assets.
    net = Network(
        height=height,
        width="100%",
        bgcolor="#070b12",
        font_color="#eef2f7",
        cdn_resources="in_line",
    )
    net.toggle_physics(False)
    for n, data in g.nodes(data=True):
        x, y = pos[n]
        market = data.get("market") or (n.split(":", 1)[0] if ":" in n else "")
        net.add_node(
            n,
            label=n.split(":", 1)[-1][:18],
            title=n,
            x=float(x) * 800,
            y=float(y) * 800,
            physics=False,
            color=MARKET_COLOR.get(market, "#1abc9c"),
        )
    for a, b, data in g.edges(data=True):
        cross = bool(data.get("cross_market"))
        net.add_edge(
            a,
            b,
            color=CROSS_EDGE if cross else SAME_EDGE,
            width=3 if cross else 1,
            title=f"{data['weight']:.3f}{' cross-market' if cross else ''}",
        )
    net.save_graph(str(path))
    html = path.read_text(encoding="utf-8")
    if "physics" in html and '"enabled": true' in html:
        html = html.replace('"enabled": true', '"enabled": false')
        path.write_text(html, encoding="utf-8")


def run(db_path: str | Path, case_id: str, html_path: Path | None = None) -> dict:
    case = get_case(db_path, case_id)
    if case is None:
        raise SystemExit(f"unknown case {case_id}")
    threshold = float(case["threshold"])
    html_path = html_path or Path("docs/eval") / f"{case_id}_graph.html"
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        g = load_graph(conn, case_id, threshold)
        comps = cluster_components(g)
        deg, bet = centralities(g)
        persist_clusters(conn, case_id, g, comps, deg, bet)
        n_db = conn.execute(
            "SELECT COUNT(*) FROM clusters WHERE case_id = ?", (case_id,)
        ).fetchone()[0]
        reports = []
        for i, members in enumerate(comps, start=1):
            if len({g.nodes[n]["market"] for n in members}) >= 3:
                reports.append(cluster_report(conn, g, members, i, deg, bet))
        if not reports and comps:
            # largest multi-market (2+) if no 3-span exists
            for i, members in enumerate(comps, start=1):
                if len({g.nodes[n]["market"] for n in members}) >= 2:
                    reports.append(cluster_report(conn, g, members, i, deg, bet))
                    break
    render_pyvis(g, html_path)
    return {
        "case_id": case_id,
        "threshold": threshold,
        "n_nodes": g.number_of_nodes(),
        "n_edges": g.number_of_edges(),
        "n_components": len(comps),
        "n_cluster_rows": n_db,
        "n_cluster_rows_match": n_db == g.number_of_nodes(),
        "html": str(html_path),
        "multi_market": reports[:3],
    }


def main(argv: list[str] | None = None) -> int:
    import argparse

    import yaml

    parser = argparse.ArgumentParser(description="Build case actor graph (no Neo4j)")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--db", default=None)
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--html", default=None)
    args = parser.parse_args(argv)
    with open(args.config, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    db_path = args.db or cfg["paths"]["sqlite_db"]
    html = Path(args.html) if args.html else None
    summary = run(db_path, args.case_id, html)
    print("graph")
    for k in (
        "case_id",
        "threshold",
        "n_nodes",
        "n_edges",
        "n_components",
        "n_cluster_rows",
        "n_cluster_rows_match",
        "html",
    ):
        print(f"  {k}: {summary[k]}")
    print("  multi_market_clusters:")
    print(json.dumps(summary["multi_market"], indent=2, default=str)[:8000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
