"""Case-scoped CSV / JSON / PDF exports (SPEC.md §15)."""

from __future__ import annotations

import csv
import json
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import networkx as nx

from src.explain.reason import FRAMING, explain_pair
from src.explain.trail import build_evidence_trail
from src.graph.build import (
    centralities,
    cluster_components,
    cluster_report,
    load_graph,
    node_key,
    present_nodes,
    shared_evidence_with_lineage,
)
from src.pipeline.case import get_case, set_status

PDF_TOP_CLUSTERS = 10

ETHICS_STATEMENT = (
    "SUTRANETRA operates on historical, publicly archived forum data only. "
    "The build never interacts with live criminal marketplaces or third-party hidden services. "
    "The only hidden service scanned is a team-owned localhost demo target, deliberately "
    "misconfigured to demonstrate OpSec leak detection. Certificate Transparency lookups "
    "use public-by-design CT logs, cache-first, with live queries opt-in. "
    "The intended use is law-enforcement-style attribution research: wallets, PGP fingerprints, "
    "and handles are reported as pseudonymous identifiers with a confidence score, never as "
    "identity verdicts."
)

EVAL_METRICS = {
    "profile": "dev",
    "model": "LogisticRegression (learned, not heuristic)",
    "held_out_pr_auc": 0.768,
    "threshold": 0.83,
    "held_out_precision_at_threshold": 1.0,
    "held_out_recall_at_threshold": 0.0149,
    "note": "Headline metric is PR-AUC, not threshold recall.",
}


def _open(db: sqlite3.Connection | str | Path) -> tuple[sqlite3.Connection, bool]:
    if isinstance(db, sqlite3.Connection):
        db.row_factory = sqlite3.Row
        return db, False
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    return conn, True


def _evidence_summary(items: list[dict], limit: int = 3) -> str:
    if not items:
        return ""
    bits = []
    for item in items[:limit]:
        bits.append(f"{item.get('kind', '?')}:{item.get('value', '')[:24]}")
    tail = f" (+{len(items) - limit} more)" if len(items) > limit else ""
    return "; ".join(bits) + tail


def _case_row(conn: sqlite3.Connection, case_id: str) -> dict | None:
    row = conn.execute("SELECT * FROM cases WHERE case_id = ?", (case_id,)).fetchone()
    return dict(row) if row else None


def _resolve_case(db: sqlite3.Connection | str | Path, case_id: str) -> dict | None:
    if isinstance(db, sqlite3.Connection):
        db.row_factory = sqlite3.Row
        return _case_row(db, case_id)
    return get_case(db, case_id)


def list_case_clusters(conn: sqlite3.Connection, case_id: str) -> list[dict]:
    rows = conn.execute(
        """
        SELECT c.cluster_id,
               MAX(c.confidence) AS confidence,
               COUNT(*) AS n_members,
               GROUP_CONCAT(DISTINCT a.market) AS markets
        FROM clusters c
        JOIN aliases a ON a.id = c.alias_id
        WHERE c.case_id = ?
        GROUP BY c.cluster_id
        ORDER BY confidence DESC, cluster_id ASC
        """,
        (case_id,),
    )
    out = []
    for r in rows:
        markets = sorted(set(str(r["markets"]).split(",")))
        out.append(
            {
                "cluster_id": r["cluster_id"],
                "confidence": float(r["confidence"] or 0),
                "n_members": r["n_members"],
                "markets": markets,
                "n_markets": len(markets),
            }
        )
    return out


def cluster_member_rows(conn: sqlite3.Connection, case_id: str, cluster_id: int) -> list[dict]:
    rows = conn.execute(
        """
        SELECT c.alias_id, c.confidence, a.market, a.alias, a.n_posts
        FROM clusters c
        JOIN aliases a ON a.id = c.alias_id
        WHERE c.case_id = ? AND c.cluster_id = ?
        ORDER BY c.confidence DESC, a.market, a.alias
        """,
        (case_id, cluster_id),
    )
    return [dict(r) for r in rows]


def cluster_subgraph(
    conn: sqlite3.Connection, case_id: str, cluster_id: int, threshold: float
) -> nx.Graph:
    g = load_graph(conn, case_id, threshold)
    members = conn.execute(
        """
        SELECT a.market, a.alias
        FROM clusters c
        JOIN aliases a ON a.id = c.alias_id
        WHERE c.case_id = ? AND c.cluster_id = ?
        """,
        (case_id, cluster_id),
    ).fetchall()
    nodes = {node_key(r["market"], r["alias"]) for r in members}
    return g.subgraph(present_nodes(g, list(nodes))).copy()


def search_corpus(conn: sqlite3.Connection, query: str, *, limit: int = 50) -> list[dict]:
    q = query.strip()
    if not q:
        return []
    like = f"%{q}%"
    hits: list[dict] = []
    seen: set[tuple] = set()

    def add(row: sqlite3.Row, hit_type: str, field: str) -> None:
        keys = set(row.keys())
        post_id = row["post_id"] if "post_id" in keys else None
        value = row["value"] if "value" in keys else row["alias"]
        key = (hit_type, post_id, value)
        if key in seen:
            return
        seen.add(key)
        if "context" in keys and row["context"]:
            ctx = row["context"]
        elif "body" in keys and row["body"]:
            ctx = row["body"]
        else:
            ctx = ""
        hits.append(
            {
                "hit_type": hit_type,
                "field": field,
                "market": row["market"],
                "alias": row["alias"],
                "post_id": post_id,
                "msg_id": row["msg_id"] if "msg_id" in keys else None,
                "kind": row["kind"] if "kind" in keys else None,
                "value": value,
                "source_archive": row["source_archive"] if "source_archive" in keys else None,
                "scrape_date": row["scrape_date"] if "scrape_date" in keys else None,
                "source_member_path": row["source_member_path"] if "source_member_path" in keys else None,
                "content_sha256": row["content_sha256"] if "content_sha256" in keys else None,
                "context": (ctx or "")[:240],
            }
        )

    for r in conn.execute(
        """
        SELECT e.kind, e.value, e.context, a.market, a.alias, p.id AS post_id, p.msg_id,
               p.source_archive, p.scrape_date, p.source_member_path, p.content_sha256
        FROM evidence e
        JOIN aliases a ON a.id = e.alias_id
        LEFT JOIN posts p ON p.id = e.post_id
        WHERE e.value LIKE ? OR e.context LIKE ?
        LIMIT ?
        """,
        (like, like, limit),
    ):
        add(r, "evidence", "value")

    # ponytail: 900k-row body LIKE is demo-lethal for fingerprints/wallets; skip when the query is an identifier.
    identifierish = len(q) >= 16 and " " not in q
    if not identifierish:
        for r in conn.execute(
            """
            SELECT p.id AS post_id, p.market, p.msg_id, p.alias, p.body,
                   p.source_archive, p.scrape_date, p.source_member_path, p.content_sha256
            FROM posts p
            WHERE p.alias LIKE ? OR p.body LIKE ?
            LIMIT ?
            """,
            (like, like, limit),
        ):
            add(r, "post", "body")
    elif len(hits) < limit:
        for r in conn.execute(
            """
            SELECT p.id AS post_id, p.market, p.msg_id, p.alias, p.body,
                   p.source_archive, p.scrape_date, p.source_member_path, p.content_sha256
            FROM posts p
            WHERE p.alias LIKE ?
            LIMIT ?
            """,
            (like, limit - len(hits)),
        ):
            add(r, "post", "alias")

    return hits[:limit]


def pair_shared_detail(
    conn: sqlite3.Connection, a_id: int, b_id: int, *, limit: int = 15
) -> list[dict]:
    rows = conn.execute(
        """
        SELECT e.kind, e.value, GROUP_CONCAT(e.id) AS evidence_ids
        FROM evidence e
        WHERE e.alias_id IN (?, ?)
        GROUP BY e.kind, e.value
        HAVING COUNT(DISTINCT e.alias_id) = 2
        ORDER BY e.kind, e.value
        LIMIT ?
        """,
        (a_id, b_id, limit),
    )
    out = []
    for r in rows:
        pa = conn.execute(
            """
            SELECT p.id AS post_id, p.msg_id, p.body, p.source_archive, p.scrape_date,
                   p.source_member_path, p.content_sha256
            FROM evidence e JOIN posts p ON p.id = e.post_id
            WHERE e.alias_id = ? AND e.kind = ? AND e.value = ?
            ORDER BY p.scrape_date DESC LIMIT 1
            """,
            (a_id, r["kind"], r["value"]),
        ).fetchone()
        pb = conn.execute(
            """
            SELECT p.id AS post_id, p.msg_id, p.body, p.source_archive, p.scrape_date,
                   p.source_member_path, p.content_sha256
            FROM evidence e JOIN posts p ON p.id = e.post_id
            WHERE e.alias_id = ? AND e.kind = ? AND e.value = ?
            ORDER BY p.scrape_date DESC LIMIT 1
            """,
            (b_id, r["kind"], r["value"]),
        ).fetchone()
        out.append(
            {
                "kind": r["kind"],
                "value": r["value"],
                "evidence_ids": [int(x) for x in str(r["evidence_ids"]).split(",") if x],
                "post_a": dict(pa) if pa else None,
                "post_b": dict(pb) if pb else None,
            }
        )
    return out


def _export_cluster_meta(
    conn: sqlite3.Connection,
    g: nx.Graph,
    members: list[dict],
    cluster_id: int,
    deg: dict[str, float],
    bet: dict[str, float],
) -> dict:
    nodes = [node_key(m["market"], m["alias"]) for m in members]
    comp_nodes = present_nodes(g, nodes)
    # ponytail: cluster_report scans all member posts; skip for huge components in JSON export.
    if len(members) <= 25:
        return cluster_report(conn, g, comp_nodes, cluster_id, deg, bet)
    core = max(comp_nodes, key=lambda n: (bet.get(n, 0.0), deg.get(n, 0.0))) if comp_nodes else ""
    return {
        "cluster_id": cluster_id,
        "n_members": len(members),
        "markets": sorted({m["market"] for m in members}),
        "n_markets": len({m["market"] for m in members}),
        "core_alias": core,
    }


def _trail_alias_ids(members: list[dict], *, cap: int = 25) -> list[int]:
    ranked = sorted(members, key=lambda m: (-float(m.get("confidence") or 0), m["market"], m["alias"]))
    return [m["alias_id"] for m in ranked[:cap]]


def build_report_data(
    db: sqlite3.Connection | str | Path,
    case_id: str,
    *,
    max_clusters: int | None = None,
) -> dict[str, Any]:
    conn, own = _open(db)
    try:
        case = _case_row(conn, case_id)
        if case is None:
            raise ValueError(f"unknown case {case_id}")
        threshold = float(case["threshold"])
        g = load_graph(conn, case_id, threshold)
        comps = cluster_components(g)
        deg, bet = centralities(g)
        cluster_summaries = list_case_clusters(conn, case_id)
        if max_clusters is not None:
            cluster_summaries = cluster_summaries[:max_clusters]

        clusters_out = []
        for summary in cluster_summaries:
            cid = summary["cluster_id"]
            members = cluster_member_rows(conn, case_id, cid)
            alias_ids = [m["alias_id"] for m in members]
            nodes = [node_key(m["market"], m["alias"]) for m in members]
            comp_nodes = present_nodes(g, nodes)
            sub = g.subgraph(comp_nodes).copy() if comp_nodes else nx.Graph()
            rep = _export_cluster_meta(conn, g, members, cid, deg, bet)
            trail_ids = _trail_alias_ids(members)
            trail = build_evidence_trail(conn, case_id, cluster_id=cid)
            explanation = (
                explain_pair(conn, case_id, trail_ids[0], trail_ids[1])
                if len(trail_ids) >= 2
                else None
            )
            lineage_ids = trail_ids if len(members) <= 25 else trail_ids
            clusters_out.append(
                {
                    **summary,
                    **rep,
                    "members": members,
                    "shared_evidence": shared_evidence_with_lineage(conn, lineage_ids),
                    "evidence_trail": trail,
                    "explanation": explanation,
                    "graph": {"n_nodes": sub.number_of_nodes(), "n_edges": sub.number_of_edges()},
                }
            )

        return {
            "system": "SUTRANETRA",
            "framing": FRAMING,
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "case": case,
            "threshold": threshold,
            "eval_metrics": EVAL_METRICS,
            "clusters": clusters_out,
            "opsec_findings": [
                dict(r)
                for r in conn.execute(
                    "SELECT * FROM opsec_findings WHERE case_id = ? ORDER BY id",
                    (case_id,),
                )
            ],
            "ethics_statement": ETHICS_STATEMENT,
        }
    finally:
        if own:
            conn.close()


def write_clusters_csv(db: sqlite3.Connection | str | Path, case_id: str, path: Path) -> Path:
    conn, own = _open(db)
    try:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(
                f,
                fieldnames=[
                    "case_id",
                    "cluster_id",
                    "alias",
                    "market",
                    "n_posts",
                    "confidence",
                    "evidence_summary",
                ],
            )
            w.writeheader()
            for summary in list_case_clusters(conn, case_id):
                cid = summary["cluster_id"]
                members = cluster_member_rows(conn, case_id, cid)
                alias_ids = [m["alias_id"] for m in members]
                shared = shared_evidence_with_lineage(conn, alias_ids[:25])
                summary_str = _evidence_summary(shared)
                for m in members:
                    w.writerow(
                        {
                            "case_id": case_id,
                            "cluster_id": cid,
                            "alias": m["alias"],
                            "market": m["market"],
                            "n_posts": m["n_posts"],
                            "confidence": m["confidence"],
                            "evidence_summary": summary_str,
                        }
                    )
        return path
    finally:
        if own:
            conn.close()


def write_report_json(db: sqlite3.Connection | str | Path, case_id: str, path: Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = build_report_data(db, case_id)
    path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    case = _resolve_case(db, case_id)
    if case:
        set_status(db, case_id, case["status"], report_path=str(path))
    return path


def _cluster_png(sub: nx.Graph, path: Path) -> None:
    import matplotlib.pyplot as plt

    path.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(6.5, 4.5), facecolor="#0a0e17")
    ax.set_facecolor("#0a0e17")
    if sub.number_of_nodes() == 0:
        ax.text(0.5, 0.5, "empty cluster", ha="center", va="center", color="#8b95a5")
        ax.axis("off")
    else:
        pos = nx.spring_layout(sub, seed=0)
        markets = {sub.nodes[n].get("market", "") for n in sub.nodes}
        palette = ["#c9a227", "#3d8bfd", "#2ecc71", "#e67e22", "#9b59b6"]
        color_map = {m: palette[i % len(palette)] for i, m in enumerate(sorted(markets))}
        node_colors = [color_map.get(sub.nodes[n].get("market", ""), "#888") for n in sub.nodes]
        nx.draw_networkx_nodes(sub, pos, node_color=node_colors, node_size=280, ax=ax)
        cross = [
            (u, v)
            for u, v, d in sub.edges(data=True)
            if d.get("cross_market")
        ]
        same = [(u, v) for u, v in sub.edges() if (u, v) not in cross and (v, u) not in cross]
        nx.draw_networkx_edges(sub, pos, edgelist=same, edge_color="#5d6d7e", width=1.0, ax=ax)
        nx.draw_networkx_edges(sub, pos, edgelist=cross, edge_color="#d35400", width=2.2, ax=ax)
        labels = {n: n.split(":", 1)[-1][:12] for n in sub.nodes}
        nx.draw_networkx_labels(sub, pos, labels=labels, font_size=6, font_color="#eef2f7", ax=ax)
        ax.axis("off")
    fig.savefig(path, dpi=130, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)


def write_report_pdf(db: sqlite3.Connection | str | Path, case_id: str, path: Path) -> Path:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = build_report_data(db, case_id, max_clusters=PDF_TOP_CLUSTERS)
    styles = getSampleStyleSheet()
    title = ParagraphStyle(
        "Title",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=22,
        textColor=colors.HexColor("#0a0e17"),
        spaceAfter=12,
    )
    body = ParagraphStyle(
        "Body",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=10,
        leading=14,
    )
    mono = ParagraphStyle("Mono", parent=body, fontName="Courier", fontSize=8, leading=10)

    doc = SimpleDocTemplate(str(path), pagesize=letter, topMargin=0.7 * inch, bottomMargin=0.7 * inch)
    story: list[Any] = []
    story.append(Paragraph("SUTRANETRA", title))
    story.append(Paragraph("The eye that follows the hidden threads.", body))
    story.append(Spacer(1, 0.2 * inch))
    case = data["case"]
    story.append(
        Paragraph(
            f"<b>Case</b> {case['case_id']} · threshold {case['threshold']} · "
            f"model {case['model_version']} · status {case['status']}",
            body,
        )
    )
    story.append(Paragraph(f"<b>Corpus</b> {case['corpus_snapshot']}", mono))
    story.append(Spacer(1, 0.25 * inch))
    story.append(Paragraph("<b>Methodology</b>", body))
    story.append(
        Paragraph(
            "SUTRANETRA fuses char n-gram stylometry, MiniLM embeddings, saturating hard-evidence "
            "matches (PGP, wallets, onions, clearnet), and posting-hour overlap via a learned "
            "logistic model. Clusters are connected components above the case threshold. "
            "OpSec scanning and CT pivots extend outward only from observed clearnet leaks.",
            body,
        )
    )
    story.append(Spacer(1, 0.2 * inch))
    story.append(Paragraph("<b>Ethics</b>", body))
    story.append(Paragraph(data["ethics_statement"], body))
    story.append(Spacer(1, 0.2 * inch))
    story.append(Paragraph("<b>Evaluation metrics (dev profile)</b>", body))
    em = data["eval_metrics"]
    story.append(
        Paragraph(
            f"PR-AUC {em['held_out_pr_auc']} · precision@{em['threshold']} "
            f"{em['held_out_precision_at_threshold']} · recall {em['held_out_recall_at_threshold']} · "
            f"{em['note']}",
            body,
        )
    )

    conn_count, own_count = _open(db)
    try:
        total_clusters = len(list_case_clusters(conn_count, case_id))
    finally:
        if own_count:
            conn_count.close()

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        for cluster in data["clusters"]:
            story.append(Spacer(1, 0.35 * inch))
            story.append(
                Paragraph(
                    f"<b>Cluster {cluster['cluster_id']}</b> — {cluster['n_members']} members · "
                    f"markets {', '.join(cluster['markets'])} · confidence "
                    f"{cluster.get('confidence', 0):.2f}",
                    body,
                )
            )
            sub = nx.Graph()
            conn, own = _open(db)
            try:
                sub = cluster_subgraph(conn, case_id, cluster["cluster_id"], float(case["threshold"]))
            finally:
                if own:
                    conn.close()
            png = tmp_path / f"c{cluster['cluster_id']}.png"
            _cluster_png(sub, png)
            if png.exists() and png.stat().st_size > 0:
                story.append(Image(str(png), width=5.8 * inch, height=3.6 * inch))

            ev_rows = [["kind", "value", "n_aliases", "lineage"]]
            for item in (cluster.get("shared_evidence") or [])[:8]:
                lineage = (
                    f"{item.get('source_archive')} / {item.get('scrape_date')} / "
                    f"{item.get('source_member_path')}"
                )
                ev_rows.append(
                    [
                        item.get("kind", ""),
                        str(item.get("value", ""))[:40],
                        str(item.get("n_aliases", "")),
                        lineage[:80],
                    ]
                )
            if len(ev_rows) > 1:
                tbl = Table(ev_rows, colWidths=[0.9 * inch, 1.6 * inch, 0.7 * inch, 3.0 * inch])
                tbl.setStyle(
                    TableStyle(
                        [
                            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a2233")),
                            ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                            ("FONTSIZE", (0, 0), (-1, -1), 7),
                            ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                        ]
                    )
                )
                story.append(tbl)

            story.append(Spacer(1, 0.1 * inch))
            story.append(Paragraph("<b>Evidence Trail</b>", body))
            for step in cluster.get("evidence_trail") or []:
                story.append(Paragraph(f"• [{step['type']}] {step['label']}", mono))
            expl = cluster.get("explanation") or {}
            if expl.get("template_sentence"):
                story.append(Spacer(1, 0.08 * inch))
                story.append(Paragraph(expl["template_sentence"], body))

        if total_clusters > PDF_TOP_CLUSTERS:
            story.append(
                Paragraph(
                    f"<i>PDF shows top {PDF_TOP_CLUSTERS} of {total_clusters} clusters; "
                    "full JSON export contains all clusters.</i>",
                    body,
                )
            )

        doc.build(story)

    case_row = get_case(db, case_id)
    if case_row:
        set_status(db, case_id, case_row["status"], report_path=str(path))
    return path
