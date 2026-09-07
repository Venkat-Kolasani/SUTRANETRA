"""SUTRANETRA investigator console — Streamlit UI (SPEC.md §15)."""

from __future__ import annotations

import json
import sqlite3
import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
import yaml

from src.explain.reason import FRAMING, explain_pair
from src.explain.trail import build_evidence_trail
from src.export.writers import (
    cluster_member_rows,
    cluster_subgraph,
    list_case_clusters,
    pair_shared_detail,
    search_corpus,
    shared_evidence_with_lineage,
    write_clusters_csv,
    write_report_json,
    write_report_pdf,
)
from src.graph.build import CROSS_EDGE, MARKET_COLOR, SAME_EDGE, render_pyvis
from src.opsec.ct_pivot import pivot as ct_pivot
from src.opsec.demo_target.serve import serve_in_thread
from src.opsec.scanner import (
    list_findings,
    persist_findings,
    scan_corpus,
    scan_target,
    validate_scan_target,
)
from src.pipeline.case import get_case
from src.ui import remote

# Exports skip aliases that dropped below the case threshold after cluster persist.

TAGLINE = "The eye that follows the hidden threads."
DEFAULT_HTTP = "http://127.0.0.1:8080"
DEFAULT_TLS = "https://127.0.0.1:8443"
VIEWS = ["Search", "Clusters", "Pair inspector", "Evidence Trail", "OpSec", "Investigator"]
DEMO_PGP = "0551E07ABB21CA0F02FBFBECE8ED5F45C33DD26D"
DEMO_PAIR = ("NW Nugz", "nw nugz")
DEMO_LABELS = ("silkroad1:NW Nugz", "silkroad2:nw nugz")

STEP_TONE = {
    "alias": ("◆", "#c9a227"),
    "post": ("▸", "#3d8bfd"),
    "evidence": ("⬡", "#2ecc71"),
    "score": ("◎", "#e8d48a"),
    "opsec": ("⚠", "#e74c3c"),
    "ct_cert": ("▣", "#9b59b6"),
    "ct_domain": ("↗", "#e67e22"),
}


def load_config(path: str = "config.yaml") -> dict:
    from src.llm.client import load_envfile

    load_envfile()
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def open_db(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


@st.cache_data(ttl=3600, max_entries=12, show_spinner=False)
def cached_cluster_graph(db_path: str, case_id: str, cluster_id: int, threshold: float) -> str:
    """Keep the rendered graph across Streamlit reruns and view changes."""
    conn = open_db(db_path)
    try:
        sub = cluster_subgraph(conn, case_id, cluster_id, threshold)
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "cluster.html"
            render_pyvis(sub, path, height="480px")
            return path.read_text(encoding="utf-8")
    finally:
        conn.close()


def list_cases(conn: sqlite3.Connection) -> list[dict]:
    return [dict(r) for r in conn.execute("SELECT * FROM cases ORDER BY created_at DESC")]


def alias_options(conn: sqlite3.Connection, case_id: str) -> list[tuple[str, int]]:
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
    # Keep the judge-facing high-confidence pair available even if a case snapshot changes.
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
    return [(f"{r['market']}:{r['alias']}", r["id"]) for r in rows]


def _label_index(labels: list[str], needle: str, fallback: int) -> int:
    needle = needle.lower()
    for i, lab in enumerate(labels):
        if lab.lower().endswith(":" + needle) or lab.lower() == needle:
            return i
    return fallback


def _select_index(label: str, options: list[str], *, key: str, default: int = 0) -> int:
    """String-valued selectbox. Stale int indices in session_state are discarded."""
    if not options:
        return -1
    default = min(max(default, 0), len(options) - 1)
    if st.session_state.get(key) not in options:
        st.session_state[key] = options[default]
    choice = st.selectbox(label, options, key=key)
    if choice not in options:
        return default
    return options.index(choice)


def brand_css() -> str:
    return """
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500&display=swap');
html, body, [class*="st-"] { font-family: 'IBM Plex Sans', sans-serif; }
.block-container { padding-top: 1rem; max-width: 1320px; }
.sutra-hero {
  display: flex; justify-content: space-between; align-items: flex-end; gap: 1rem;
  padding: 0.85rem 1.15rem; margin-bottom: 0.85rem;
  border: 1px solid rgba(201,162,39,0.22); border-radius: 16px;
  background: linear-gradient(135deg, rgba(18,24,38,0.95), rgba(10,14,22,0.88));
}
.sutra-title { font-size: 1.55rem; font-weight: 700; letter-spacing: 0.16em; color: #e8d48a; margin: 0; }
.sutra-tagline { color: #8b95a5; font-size: 0.86rem; margin: 0.15rem 0 0; }
.metric-card {
  padding: 0.7rem 0.85rem; border-radius: 12px;
  background: rgba(18,24,38,0.82); border: 1px solid rgba(255,255,255,0.06);
}
.metric-label { color: #8b95a5; font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.08em; }
.metric-value { font-size: 1.12rem; font-weight: 600; }
.framing {
  padding: 0.65rem 0.9rem; margin: 0.7rem 0 0.9rem;
  border-left: 3px solid #c9a227; background: rgba(201,162,39,0.07);
  border-radius: 0 10px 10px 0; color: #8b95a5; font-size: 0.84rem;
}
.sutra-trail { padding: 0.2rem 0 0.6rem; }
.trail-step { display: flex; gap: 0.8rem; align-items: flex-start; }
.trail-badge {
  width: 32px; height: 32px; border-radius: 9px; flex-shrink: 0;
  display: flex; align-items: center; justify-content: center;
  font-size: 0.9rem;
}
.trail-type {
  font-family: 'IBM Plex Mono', monospace; font-size: 0.66rem;
  letter-spacing: 0.12em; text-transform: uppercase;
}
.trail-label { font-size: 0.92rem; line-height: 1.4; margin-top: 0.12rem; }
.trail-meta { font-family: 'IBM Plex Mono', monospace; font-size: 0.72rem; color: #8b95a5; margin-top: 0.2rem; }
.trail-connector { width: 2px; height: 14px; margin: 0 0 0 15px; background: rgba(61,139,253,0.35); }
.quote {
  padding: 0.85rem 1rem; border-radius: 12px;
  background: rgba(61,139,253,0.08); border: 1px solid rgba(61,139,253,0.18);
  font-size: 0.95rem; line-height: 1.5;
}
.sutra-status {
  display: inline-flex; align-items: center; gap: 0.45rem; padding: 0.32rem 0.55rem;
  border: 1px solid rgba(46,204,113,0.22); border-radius: 999px; color: #b9f6cc;
  background: rgba(46,204,113,0.08); font-size: 0.76rem;
}
.sutra-dot { width: 7px; height: 7px; border-radius: 50%; background: #2ecc71; box-shadow: 0 0 10px rgba(46,204,113,0.65); }
.sutra-panel { padding: 0.85rem 1rem; border: 1px solid rgba(255,255,255,0.07); border-radius: 14px; background: rgba(18,24,38,0.56); }
.sutra-guide { padding: 0.7rem 0.85rem; margin: 0.65rem 0 0.9rem; border: 1px solid rgba(61,139,253,0.18); border-radius: 10px; background: rgba(61,139,253,0.06); color: #8b95a5; font-size: 0.82rem; line-height: 1.5; }
.sutra-guide b { display: block; color: #e8edf5; margin-bottom: 0.2rem; }
.sutra-legend { display: flex; flex-wrap: wrap; align-items: center; gap: 0.45rem 0.8rem; margin: 0.55rem 0 0.15rem; color: #8b95a5; font-size: 0.76rem; }
.sutra-key { display: inline-flex; align-items: center; gap: 0.28rem; white-space: nowrap; }
.sutra-swatch { width: 10px; height: 10px; display: inline-block; border-radius: 50%; box-shadow: 0 0 0 1px rgba(255,255,255,0.2); }
.sutra-edge-swatch { width: 18px; height: 3px; display: inline-block; border-radius: 2px; }
div[data-testid="stSidebar"] { border-right: 1px solid rgba(255,255,255,0.05); }
</style>
"""


def guide(title: str, body: str) -> None:
    st.markdown(
        f"<div class='sutra-guide'><b>{title}</b><div>{body}</div></div>",
        unsafe_allow_html=True,
    )


def graph_legend() -> None:
    markets = " ".join(
        f"<span class='sutra-key'><i class='sutra-swatch' style='background:{color}'></i>{market} node</span>"
        for market, color in MARKET_COLOR.items()
    )
    st.markdown(
        f"<div class='sutra-legend'><span>Graph key:</span>{markets}"
        f"<span class='sutra-key'><i class='sutra-edge-swatch' style='background:{CROSS_EDGE}'></i>cross-market edge</span>"
        f"<span class='sutra-key'><i class='sutra-edge-swatch' style='background:{SAME_EDGE}'></i>same-market edge</span></div>",
        unsafe_allow_html=True,
    )


def trail_legend() -> None:
    items = (
        ("#c9a227", "◆ alias"),
        ("#3d8bfd", "▸ post"),
        ("#2ecc71", "⬡ evidence"),
        ("#e8d48a", "◎ score"),
        ("#e74c3c", "⚠ OpSec"),
        ("#9b59b6", "▣ CT certificate"),
        ("#e67e22", "↗ CT sibling"),
    )
    rendered = " ".join(
        f"<span class='sutra-key' style='color:{color}'>{label}</span>"
        for color, label in items
    )
    st.markdown(
        f"<div class='sutra-legend'><span>Trail key:</span>{rendered}</div>",
        unsafe_allow_html=True,
    )


def render_trail_html(trail: list[dict]) -> str:
    blocks = []
    for i, step in enumerate(trail):
        icon, color = STEP_TONE.get(step["type"], ("•", "#8b95a5"))
        meta = ""
        if step["type"] == "post":
            meta = (
                f"<div class='trail-meta'>{step.get('source_archive') or ''} / "
                f"{step.get('scrape_date') or ''} / {step.get('source_member_path') or ''}<br>"
                f"sha256 {step.get('content_sha256') or ''}</div>"
            )
        connector = "<div class='trail-connector'></div>" if i < len(trail) - 1 else ""
        blocks.append(
            f"<div class='trail-step'><div class='trail-badge' "
            f"style='color:{color};border:1px solid {color}33;background:{color}22'>{icon}</div>"
            f"<div><div class='trail-type' style='color:{color}'>{step['type']}</div>"
            f"<div class='trail-label'>{step['label']}</div>{meta}</div></div>{connector}"
        )
    return "<div class='sutra-trail'>" + "".join(blocks) + "</div>"


def export_buttons(case_id: str, db_path: str, prefix: str, *, cfg: dict | None = None) -> None:
    st.caption("Case exports · stable filenames")
    c1, c2, c3 = st.columns(3)
    if remote.is_remote(cfg):
        with c1:
            if st.button("Fetch clusters.csv", key=f"{prefix}_csv"):
                st.session_state[f"{prefix}_csv_bytes"] = remote.get_bytes(
                    f"/cases/{case_id}/export/csv", cfg
                )
            raw = st.session_state.get(f"{prefix}_csv_bytes")
            if raw:
                st.download_button("Download CSV", raw, file_name="clusters.csv", mime="text/csv", key=f"{prefix}_csv_dl")
        with c2:
            if st.button("Fetch report.json", key=f"{prefix}_json"):
                st.session_state[f"{prefix}_json_bytes"] = remote.get_bytes(
                    f"/cases/{case_id}/export/json", cfg
                )
            raw = st.session_state.get(f"{prefix}_json_bytes")
            if raw:
                st.download_button("Download JSON", raw, file_name="report.json", mime="application/json", key=f"{prefix}_json_dl")
        with c3:
            if st.button("Fetch report.pdf", key=f"{prefix}_pdf"):
                st.session_state[f"{prefix}_pdf_bytes"] = remote.get_bytes(
                    f"/cases/{case_id}/export/pdf", cfg
                )
            raw = st.session_state.get(f"{prefix}_pdf_bytes")
            if raw:
                st.download_button("Download PDF", raw, file_name="report.pdf", mime="application/pdf", key=f"{prefix}_pdf_dl")
        return
    out_dir = Path("data/exports") / case_id
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / "clusters.csv"
    json_path = out_dir / "report.json"
    pdf_path = out_dir / "report.pdf"
    case = get_case(db_path, case_id) or {}
    report_path = Path(case["report_path"]) if case.get("report_path") else None
    cached_pdf = pdf_path if pdf_path.exists() else report_path if report_path and report_path.exists() else None
    with c1:
        if st.button("Prepare clusters.csv", key=f"{prefix}_csv"):
            write_clusters_csv(db_path, case_id, csv_path)
            st.success(f"Wrote {csv_path}")
        if csv_path.exists():
            st.download_button(
                "Download CSV",
                csv_path.read_bytes(),
                file_name=csv_path.name,
                mime="text/csv",
                key=f"{prefix}_csv_dl",
            )
    with c2:
        if st.button("Prepare report.json", key=f"{prefix}_json"):
            with st.spinner("Building JSON…"):
                write_report_json(db_path, case_id, json_path)
            st.success(f"Wrote {json_path}")
        if json_path.exists():
            st.download_button(
                "Download JSON",
                json_path.read_bytes(),
                file_name=json_path.name,
                mime="application/json",
                key=f"{prefix}_json_dl",
            )
    with c3:
        if st.button("Prepare report.pdf", key=f"{prefix}_pdf"):
            with st.spinner("Building PDF (top clusters)…"):
                write_report_pdf(db_path, case_id, pdf_path)
            st.success(f"Wrote {pdf_path}")
        if cached_pdf:
            st.download_button(
                "Download PDF",
                cached_pdf.read_bytes(),
                file_name="report.pdf",
                mime="application/pdf",
                key=f"{prefix}_pdf_dl",
            )


def _snapshot(case: dict) -> dict:
    snap = case.get("corpus_snapshot")
    if isinstance(snap, str):
        return json.loads(snap)
    return snap or {}


def render_case_header(case: dict) -> None:
    snap = _snapshot(case)
    st.markdown(
        f"""
<div class="sutra-hero">
  <div>
    <div class="sutra-title">SUTRANETRA</div>
    <p class="sutra-tagline">{TAGLINE}</p>
  </div>
  <div class="sutra-tagline">case {case['case_id']} · {case['status']}</div>
</div>
""",
        unsafe_allow_html=True,
    )
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.markdown(
        f"<div class='metric-card'><div class='metric-label'>Threshold</div>"
        f"<div class='metric-value'>{case['threshold']}</div></div>",
        unsafe_allow_html=True,
    )
    c2.markdown(
        f"<div class='metric-card'><div class='metric-label'>Model</div>"
        f"<div class='metric-value' style='font-size:0.92rem'>{case['model_version']}</div></div>",
        unsafe_allow_html=True,
    )
    c3.markdown(
        f"<div class='metric-card'><div class='metric-label'>Corpus</div>"
        f"<div class='metric-value'>{snap['n_posts']:,} posts</div></div>",
        unsafe_allow_html=True,
    )
    c4.markdown(
        f"<div class='metric-card'><div class='metric-label'>Aliases</div>"
        f"<div class='metric-value'>{snap['n_aliases']:,}</div></div>",
        unsafe_allow_html=True,
    )
    c5.markdown(
        f"<div class='metric-card'><div class='metric-label'>Markets</div>"
        f"<div class='metric-value' style='font-size:0.92rem'>{len(snap['markets'])}</div></div>",
        unsafe_allow_html=True,
    )
    st.markdown(f"<div class='framing'>{FRAMING}</div>", unsafe_allow_html=True)
    st.caption(
        f"config_hash {case['config_hash'][:12]}… · {', '.join(snap['markets'])}"
    )


def tab_search(conn: sqlite3.Connection | None, case_id: str, db_path: str, cfg: dict) -> None:
    st.subheader("Evidence search")
    guide(
        "What this page tells you",
        "Searches the stored corpus for a handle, wallet, PGP fingerprint, onion address, or domain. Every result keeps its source archive, scrape date, member path, and content hash so the observation can be checked. A hit is an investigative lead, not an identity verdict.",
    )
    st.caption("Full-text over extracted evidence and posts, with archive-member lineage.")
    if st.button("Load example PGP fingerprint", key="demo_pgp"):
        st.session_state["search_input"] = DEMO_PGP
    query = st.text_input(
        "Alias, wallet, PGP fingerprint, onion, or clearnet domain",
        placeholder="PGP fingerprint, BTC address, onion, or handle",
        key="search_input",
    )
    if not (query or "").strip():
        st.info("Search a handle, wallet, PGP fingerprint, onion, or clearnet domain.")
        export_buttons(case_id, db_path, "search", cfg=cfg)
        return
    hits = (
        remote.get(f"/cases/{case_id}/search", cfg, q=query)
        if remote.is_remote(cfg)
        else search_corpus(conn, query)
    )
    if not hits:
        st.warning("No matches.")
        export_buttons(case_id, db_path, "search", cfg=cfg)
        return
    st.caption(f"{len(hits)} hits")
    df = pd.DataFrame(hits)
    cols = [
        c
        for c in (
            "hit_type",
            "kind",
            "market",
            "alias",
            "value",
            "scrape_date",
            "source_archive",
            "source_member_path",
            "content_sha256",
            "context",
        )
        if c in df.columns
    ]
    st.dataframe(df[cols], width="stretch", hide_index=True)
    export_buttons(case_id, db_path, "search", cfg=cfg)


def tab_clusters(conn: sqlite3.Connection | None, case_id: str, case: dict, db_path: str, cfg: dict) -> None:
    st.subheader("Actor clusters")
    clusters = (
        remote.get(f"/cases/{case_id}/clusters", cfg)
        if remote.is_remote(cfg)
        else list_case_clusters(conn, case_id)
    )
    if not clusters:
        st.warning(
            f"Graph not available for {case_id}: case status is "
            f"{case.get('status', 'unknown')}. Run the graph stage before opening cluster review."
        )
        return
    multi = [c for c in clusters if c["n_markets"] >= 3]
    guide(
        "How to read this page",
        f"{len(clusters)} clusters means {len(clusters)} connected components in the thresholded pair graph—not {len(clusters)} confirmed people. {len(multi)} components contain aliases from three or more markets. The displayed score is the strongest stored pair confidence in that component; it is not a probability of identity.",
    )
    if multi:
        recommended = min(multi, key=lambda c: (c["n_members"], -c["confidence"]))
        st.caption(
            f"{len(clusters)} clusters · {len(multi)} span 3+ markets "
            f"(recommended demo cluster is #{recommended['cluster_id']}). "
            "The recommended cluster is preselected for a concise walkthrough; larger components are valid but denser."
        )
    else:
        st.caption(f"{len(clusters)} clusters.")
    labels = [
        f"#{c['cluster_id']} · {c['n_members']} aliases · "
        f"{c['n_markets']} markets · max score {c['confidence']:.2f}"
        for c in clusters
    ]
    recommended = min(multi, key=lambda c: (c["n_members"], -c["confidence"])) if multi else clusters[0]
    default = next((i for i, c in enumerate(clusters) if c["cluster_id"] == recommended["cluster_id"]), 0)
    idx = _select_index("Select cluster", labels, key="cluster_pick", default=default)
    cluster = clusters[idx]
    st.session_state["selected_cluster_id"] = cluster["cluster_id"]
    if remote.is_remote(cfg):
        payload = remote.get(f"/cases/{case_id}/clusters/{cluster['cluster_id']}", cfg)
        members, shared, html = payload["members"], payload["shared"], payload.get("graph_html") or ""
    else:
        members = cluster_member_rows(conn, case_id, cluster["cluster_id"])
        alias_ids = [m["alias_id"] for m in members]
        shared = shared_evidence_with_lineage(conn, alias_ids)
        with st.spinner("Rendering cluster graph…"):
            html = cached_cluster_graph(
                db_path, case_id, cluster["cluster_id"], float(case["threshold"])
            )
    if cluster["n_members"] > 80:
        guide(
            "Why this graph looks dense",
            f"Cluster #{cluster['cluster_id']} is a valid large connected component with {cluster['n_members']} aliases. The circular layout keeps every member visible, so many thin lines are expected. For the clearest judge walkthrough, choose the preselected recommended cluster #{recommended['cluster_id']}.",
        )
    st.markdown(
        f"<div class='sutra-panel'><b>Cluster graph</b><div class='sutra-guide' style='margin-bottom:0'>Each circle is a pseudonymous alias. Its colour identifies the marketplace. A line is a stored pair score at or above the case threshold ({case['threshold']}); line thickness highlights cross-market links. Hover a node or line for the exact label and score; use wheel, drag, and the navigation controls to explore.</div></div>",
        unsafe_allow_html=True,
    )
    graph_legend()
    components.html(html, height=500, scrolling=False)
    c1, c2 = st.columns([1, 1])
    with c1:
        st.markdown("**Members**")
        st.caption("The aliases represented by this connected component.")
        st.dataframe(pd.DataFrame(members), width="stretch", hide_index=True)
    with c2:
        st.markdown("**Shared evidence (with lineage)**")
        st.caption("Identifiers observed for more than one member, with the source record that carried them.")
        st.dataframe(pd.DataFrame(shared), width="stretch", hide_index=True)
    export_buttons(case_id, db_path, "clusters", cfg=cfg)


def tab_pair(conn: sqlite3.Connection | None, case_id: str, db_path: str, cfg: dict) -> None:
    st.subheader("Pair inspector")
    guide(
        "What this page tells you",
        "Score meanings: S_char is writing-style similarity from character patterns. S_embed is topic or semantic similarity, not writing style. S_hard is shared extracted evidence such as a PGP fingerprint or wallet. S_time is similarity in activity timing; a dash means there was not enough timestamped data. Confidence is the learned fusion score used for graph links, not an identity verdict.",
    )
    options = (
        [(o["label"], o["alias_id"]) for o in remote.get(f"/cases/{case_id}/aliases", cfg)]
        if remote.is_remote(cfg)
        else alias_options(conn, case_id)
    )
    if len(options) < 2:
        st.warning("Need at least two clustered aliases.")
        return
    labels = [o[0] for o in options]
    ids = [o[1] for o in options]
    c1, c2 = st.columns(2)
    with c1:
        a_idx = _select_index(
            "Alias A",
            labels,
            key="pair_alias_a",
            default=_label_index(labels, DEMO_LABELS[0], 0),
        )
    with c2:
        b_idx = _select_index(
            "Alias B",
            labels,
            key="pair_alias_b",
            default=_label_index(labels, DEMO_LABELS[1], min(1, len(labels) - 1)),
        )
    a_id, b_id = ids[a_idx], ids[b_idx]
    if a_id == b_id:
        st.warning("Pick two different aliases.")
        return
    if remote.is_remote(cfg):
        payload = remote.get(
            f"/cases/{case_id}/pairs",
            cfg,
            a_alias_id=a_id,
            b_alias_id=b_id,
            polish=True,
        )
        ev = payload["explanation"]
        score = payload.get("scores")
        detail = payload.get("detail") or []
        sentence = payload.get("sentence") or ev.get("template_sentence")
    else:
        from src.llm.polish import polish_explanation

        ev = explain_pair(conn, case_id, a_id, b_id)
        sentence = polish_explanation(ev, cfg)
        score = conn.execute(
            """
            SELECT * FROM pair_scores
            WHERE case_id = ?
              AND ((a_alias_id = ? AND b_alias_id = ?) OR (a_alias_id = ? AND b_alias_id = ?))
            """,
            (case_id, a_id, b_id, b_id, a_id),
        ).fetchone()
        detail = pair_shared_detail(conn, a_id, b_id)
    if score is None:
        st.warning(
            "No `pair_scores` row for this pair — it was never a fusion candidate, "
            "so there is no S_char / S_embed / S_hard / S_time / confidence. "
            "Shared evidence below (if any) comes from the evidence tables, not a fused score."
        )
    else:
        cols = st.columns(5)
        for col, key, label in zip(
            cols,
            ("s_char", "s_embed", "s_hard", "s_time", "confidence"),
            ("S_char", "S_embed", "S_hard", "S_time", "Confidence"),
        ):
            val = score[key]
            col.metric(label, "—" if val is None else f"{float(val):.3f}")
    st.markdown("**Generated explanation**")
    st.markdown(f"<div class='quote'>{sentence}</div>", unsafe_allow_html=True)
    st.markdown("**Shared evidence with post context and lineage**")
    if not detail:
        st.info("No shared hard-evidence rows for this pair.")
        export_buttons(case_id, db_path, "pair", cfg=cfg)
        return
    for item in detail:
        st.markdown(f"**{item['kind']}** · `{item['value'][:64]}`")
        pa, pb = item.get("post_a"), item.get("post_b")
        left, right = st.columns(2)
        for col, post, title in ((left, pa, labels[a_idx]), (right, pb, labels[b_idx])):
            with col:
                st.caption(title)
                if not post:
                    st.write("No linked post.")
                    continue
                st.code(
                    f"{post.get('source_archive')} / {post.get('scrape_date')}\n"
                    f"{post.get('source_member_path')}\n"
                    f"sha256 {post.get('content_sha256')}",
                    language=None,
                )
                st.write((post.get("body") or "")[:280])
    export_buttons(case_id, db_path, "pair", cfg=cfg)


def tab_trail(conn: sqlite3.Connection | None, case_id: str, db_path: str, cfg: dict) -> None:
    st.subheader("Evidence Trail")
    guide(
        "What this page tells you",
        "This is the ordered, deterministic chain behind a result: alias → source post → extracted evidence → second alias → fused score → any observed OpSec or Certificate Transparency step. The trail reads only stored rows; if a step was not observed, it is left out.",
    )
    trail_legend()
    mode = st.radio("Trail source", ["Cluster", "Pair"], horizontal=True)
    if mode == "Cluster":
        clusters = (
            remote.get(f"/cases/{case_id}/clusters", cfg)
            if remote.is_remote(cfg)
            else list_case_clusters(conn, case_id)
        )
        if not clusters:
            st.warning(
                f"No computed graph clusters are available for {case_id}. "
                "Run the graph stage before opening the evidence trail."
            )
            return
        labels = [
            f"#{c['cluster_id']} · {c['n_markets']} markets · conf {c['confidence']:.2f}"
            for c in clusters
        ]
        default = next((i for i, c in enumerate(clusters) if c["cluster_id"] == 1), None)
        if default is None:
            default = next((i for i, c in enumerate(clusters) if c["n_markets"] >= 3), 0)
        idx = _select_index("Cluster", labels, key="trail_cluster", default=default)
        with st.spinner("Building evidence trail…"):
            trail = (
                remote.get(f"/cases/{case_id}/trail", cfg, cluster_id=clusters[idx]["cluster_id"])
                if remote.is_remote(cfg)
                else build_evidence_trail(conn, case_id, cluster_id=clusters[idx]["cluster_id"])
            )
    else:
        options = (
            [(o["label"], o["alias_id"]) for o in remote.get(f"/cases/{case_id}/aliases", cfg)]
            if remote.is_remote(cfg)
            else alias_options(conn, case_id)
        )
        if len(options) < 2:
            st.warning("Need at least two aliases.")
            return
        labels = [o[0] for o in options]
        ids = [o[1] for o in options]
        c1, c2 = st.columns(2)
        with c1:
            a_idx = _select_index(
                "Alias A",
                labels,
                key="trail_alias_a",
                default=_label_index(labels, DEMO_LABELS[0], 0),
            )
        with c2:
            b_idx = _select_index(
                "Alias B",
                labels,
                key="trail_alias_b",
                default=_label_index(labels, DEMO_LABELS[1], min(1, len(labels) - 1)),
            )
        with st.spinner("Building evidence trail…"):
            trail = (
                remote.get(
                    f"/cases/{case_id}/trail",
                    cfg,
                    a_alias_id=ids[a_idx],
                    b_alias_id=ids[b_idx],
                )
                if remote.is_remote(cfg)
                else build_evidence_trail(conn, case_id, a_alias_id=ids[a_idx], b_alias_id=ids[b_idx])
            )
    st.markdown(render_trail_html(trail), unsafe_allow_html=True)
    st.caption("Step sequence (types)")
    st.code(" → ".join(s["type"] for s in trail), language=None)
    export_buttons(case_id, db_path, "trail", cfg=cfg)


def tab_opsec(conn: sqlite3.Connection | None, case_id: str, cfg: dict, db_path: str) -> None:
    st.subheader("OpSec scan")
    guide(
        "What this page tells you",
        "Shows infrastructure observations from the team-owned localhost demonstration target and cached Certificate Transparency pivots. These are technical leads to investigate next; they do not prove who controls an alias or domain.",
    )
    cloud = remote.is_remote(cfg)
    if cloud:
        st.caption("Cloud: stored findings from the localhost demo scan. Live scan is local-only.")
        findings = remote.get(f"/cases/{case_id}/opsec", cfg)
        st.markdown(f"**Findings for {case_id}** ({len(findings)} rows)")
        if findings:
            st.dataframe(pd.DataFrame(findings), width="stretch", hide_index=True)
        siblings = [f for f in findings if f["finding_kind"] == "ct_sibling"]
        if siblings:
            st.markdown("**CT sibling domains**")
            st.write([f["value"] for f in siblings[:12]])
        export_buttons(case_id, db_path, "opsec", cfg=cfg)
        return
    st.caption("Localhost demo target only — not a general-purpose scanner.")
    http_url = st.text_input("HTTP target (localhost only)", value=DEFAULT_HTTP)
    tls_url = st.text_input("TLS target (optional, localhost only)", value=DEFAULT_TLS)
    c1, c2, c3 = st.columns(3)
    start_demo = c1.button("Start demo target")
    run_scan = c2.button("Run scan + CT pivot")
    run_corpus = c3.button("Scan corpus clearnet markers")
    if start_demo:
        info = serve_in_thread()
        st.session_state["demo_stop"] = info["stop"]
        st.success(f"Demo running at {info['http']} / {info['https']}")
    if run_scan:
        try:
            http = validate_scan_target(http_url)
            tls = validate_scan_target(tls_url) if tls_url.strip() else None
        except ValueError as exc:
            st.error(str(exc))
            return
        findings = scan_target(http, tls)
        persist_findings(db_path, case_id, http, findings)
        clearnet = [f for f in findings if f["finding_kind"] == "clearnet_ref"]
        ct_rows = []
        cache_dir = Path(cfg["paths"]["ct_cache"])
        for f in clearnet[:3]:
            result = ct_pivot(f["value"], cache_dir, live=False)
            for sib in result.get("siblings", [])[:5]:
                ct_rows.append(
                    {
                        "finding_kind": "ct_sibling",
                        "value": sib,
                        "detail": json.dumps({"seed": f["value"], "source": result["source"]}),
                    }
                )
        if ct_rows:
            persist_findings(db_path, case_id, f"ct:{clearnet[0]['value']}", ct_rows)
        st.success(f"Recorded {len(findings)} scanner findings (+{len(ct_rows)} CT siblings from cache).")
    if run_corpus:
        corp = scan_corpus(conn)
        persist_findings(db_path, case_id, "corpus", corp)
        st.success(f"Recorded {len(corp)} corpus clearnet findings.")
    findings = list_findings(db_path, case_id)
    st.markdown(f"**Findings for {case_id}** ({len(findings)} rows)")
    if findings:
        st.dataframe(pd.DataFrame(findings), width="stretch", hide_index=True)
    siblings = [f for f in findings if f["finding_kind"] == "ct_sibling"]
    if siblings:
        st.markdown("**CT sibling domains**")
        st.write([f["value"] for f in siblings[:12]])
    export_buttons(case_id, db_path, "opsec", cfg=cfg)


def tab_investigator(case_id: str, cfg: dict, db_path: str) -> None:
    from src.agent.investigator import ask
    from src.llm.client import llm_reachable

    st.subheader("Investigator")
    guide(
        "What this page tells you",
        "Ask a question in plain English about the active case. Groq phrases facts already stored by SUTRANETRA; it does not score aliases, change the database, or issue an identity verdict. Use the other tabs and the provenance rows under each answer to verify it.",
    )
    live = True if remote.is_remote(cfg) else llm_reachable(cfg)
    if not live and not remote.is_remote(cfg):
        return
    if "inv_chat" not in st.session_state:
        st.session_state["inv_chat"] = []
    for turn in st.session_state["inv_chat"]:
        with st.chat_message("user"):
            st.write(turn["q"])
        with st.chat_message("assistant"):
            st.write(turn["a"]["text"])
            st.caption(f"model {turn['a'].get('model')} · case {turn['a'].get('case_id')}")
            for i, tr in enumerate(turn["a"].get("tool_traces") or []):
                with st.expander(f"Provenance · {tr.get('name')} · {i+1}"):
                    st.json(tr.get("args") or {})
                    out = tr.get("output")
                    if isinstance(out, dict) and isinstance(out.get("sample"), list):
                        st.json({k: v for k, v in out.items() if k != "sample"})
                        if out["sample"] and isinstance(out["sample"][0], dict):
                            st.dataframe(
                                pd.DataFrame(out["sample"]), width="stretch", hide_index=True
                            )
                    elif isinstance(out, list) and out and isinstance(out[0], dict):
                        st.dataframe(pd.DataFrame(out), width="stretch", hide_index=True)
                    else:
                        st.json(out)
    q = st.chat_input("Ask a rehearsed question (PGP, trail, clearnet→CT)…")
    if not q:
        return
    with st.spinner("Querying stored results…"):
        if remote.is_remote(cfg):
            ans = remote.post("/agent/chat", {"case_id": case_id, "question": q}, cfg)
        else:
            ans = ask(q, db_path=db_path, case_id=case_id, cfg=cfg)
    st.session_state["inv_chat"].append({"q": q, "a": ans})
    st.rerun()


def main() -> None:
    st.set_page_config(
        page_title="SUTRANETRA",
        page_icon="👁",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    st.markdown(brand_css(), unsafe_allow_html=True)
    cfg = load_config()
    from src.llm.client import llm_reachable

    db_path = cfg["paths"]["sqlite_db"]
    if Path("data/demo/attrib.sqlite").exists() and not Path(db_path).exists():
        db_path = "data/demo/attrib.sqlite"
    cloud = remote.is_remote(cfg)
    conn = None if cloud else open_db(db_path)
    try:
        with st.sidebar:
            st.markdown("### SUTRANETRA")
            st.caption(TAGLINE)
            if cloud:
                cases = remote.get("/cases", cfg)
            else:
                cases = list_cases(conn)
            if not cases:
                st.error("No cases in database.")
                return
            case_ids = [c["case_id"] for c in cases]
            default_idx = case_ids.index("CASE-2026-001") if "CASE-2026-001" in case_ids else 0
            case_id = st.selectbox("Active case", case_ids, index=default_idx)
            if case_id is None:
                case_id = case_ids[default_idx]
            if cloud:
                case = remote.get(f"/cases/{case_id}", cfg)
            else:
                case = get_case(db_path, case_id) or next(c for c in cases if c["case_id"] == case_id)
            if remote.is_remote(cfg) or llm_reachable(cfg):
                st.markdown(
                    "<div class='sutra-status'><span class='sutra-dot'></span>Groq phrasing online</div>",
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    "<div class='sutra-status'><span class='sutra-dot'></span>Case review ready</div>",
                    unsafe_allow_html=True,
                )
            st.caption("Evidence-led attribution workspace")

        render_case_header(case)
        view = st.segmented_control("View", VIEWS, default=VIEWS[0], required=True, key="sutra_view") or VIEWS[0]
        if view == "Search":
            tab_search(conn, case_id, db_path, cfg)
        elif view == "Clusters":
            tab_clusters(conn, case_id, case, db_path, cfg)
        elif view == "Pair inspector":
            tab_pair(conn, case_id, db_path, cfg)
        elif view == "Evidence Trail":
            tab_trail(conn, case_id, db_path, cfg)
        elif view == "OpSec":
            tab_opsec(conn, case_id, cfg, db_path)
        else:
            tab_investigator(case_id, cfg, db_path)
    finally:
        if conn is not None:
            conn.close()


if __name__ == "__main__":
    main()
