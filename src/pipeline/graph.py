"""LangGraph orchestration wrapper (SPEC.md §16.1). No scoring logic here."""

from __future__ import annotations

import sqlite3
import time
from contextlib import contextmanager
from operator import add
from pathlib import Path
from typing import Annotated, Any, TypedDict

import yaml
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph

from src.pipeline.case import create_case, get_case, set_status


class CaseState(TypedDict, total=False):
    case_id: str
    db_path: str
    config_path: str
    markets: list[str]
    n_posts: int
    n_aliases: int
    n_evidence: int
    candidate_pairs: int
    scored_pairs: int
    clusters: list[dict]
    opsec_findings: list[dict]
    evidence_trail: list[dict]
    errors: Annotated[list[str], add]
    timings: Annotated[list[dict], add]


def _cfg(state: CaseState) -> dict:
    with open(state.get("config_path") or "config.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _tick(name: str, t0: float) -> dict:
    t1 = time.perf_counter()
    return {"node": name, "t0": t0, "t1": t1, "elapsed": t1 - t0}


def node_ingest(state: CaseState) -> dict:
    from src.ingest.load import run as ingest_run
    from src.ingest.schema import init_db

    t0 = time.perf_counter()
    cfg = _cfg(state)
    db = state["db_path"]
    cid = state["case_id"]
    init_db(db)
    if get_case(db, cid) is None:
        create_case(db, cfg, case_id=cid)
    set_status(db, cid, "running")
    out = ingest_run(db, cfg, markets=state.get("markets") or cfg.get("markets"))
    return {
        "n_posts": out["n_posts"],
        "n_aliases": out["n_aliases"],
        "markets": list(out.get("markets") or {}),
        "timings": [_tick("ingest", t0)],
    }


def node_evidence(state: CaseState) -> dict:
    from src.evidence.extract import run as evidence_run

    t0 = time.perf_counter()
    counts = evidence_run(state["db_path"], replace=True, progress=False)
    return {
        "n_evidence": int(counts.get("evidence_rows") or 0),
        "timings": [_tick("evidence", t0)],
    }


def node_stylometry(state: CaseState) -> dict:
    from src.stylometry.char_ngram import run as char_run
    from src.stylometry.embed import run as embed_run
    from src.temporal.activity import run as time_run

    t0 = time.perf_counter()
    cfg = _cfg(state)
    sty = cfg.get("stylometry") or {}
    char = char_run(state["db_path"], sty)
    embed_run(state["db_path"], sty)
    time_run(state["db_path"])
    n = int(char.get("n_candidates") or char.get("n_pairs") or 0)
    return {"candidate_pairs": n, "timings": [_tick("stylometry", t0)]}


def node_fusion(state: CaseState) -> dict:
    from src.fusion.model import run as fusion_run

    t0 = time.perf_counter()
    cfg = _cfg(state)
    out = fusion_run(
        state["db_path"],
        cfg,
        case_id=state["case_id"],
        heuristic=bool(state.get("heuristic")),
    )
    set_status(state["db_path"], state["case_id"], "running")
    return {
        "scored_pairs": int(out.get("n_scored") or 0),
        "timings": [_tick("fusion", t0)],
    }


def node_graph(state: CaseState) -> dict:
    from src.graph.build import run as graph_run

    t0 = time.perf_counter()
    out = graph_run(state["db_path"], state["case_id"])
    clusters = list(out.get("multi_market") or [])
    if not clusters:
        with sqlite3.connect(state["db_path"]) as conn:
            n = conn.execute(
                "SELECT COUNT(DISTINCT cluster_id) FROM clusters WHERE case_id=?",
                (state["case_id"],),
            ).fetchone()[0]
            clusters = [{"cluster_id": i} for i in range(1, int(n) + 1)]
    return {"clusters": clusters, "timings": [_tick("graph", t0)]}


def node_opsec(state: CaseState) -> dict:
    from src.opsec.scanner import list_findings, persist_findings, scan_corpus

    t0 = time.perf_counter()
    db, cid = state["db_path"], state["case_id"]
    with sqlite3.connect(db) as conn:
        conn.row_factory = sqlite3.Row
        findings = scan_corpus(conn)
    persist_findings(db, cid, "corpus", findings)
    rows = list_findings(db, cid)
    return {"opsec_findings": rows, "timings": [_tick("opsec", t0)]}


def node_explain(state: CaseState) -> dict:
    from src.explain.trail import build_evidence_trail

    t0 = time.perf_counter()
    db, cid = state["db_path"], state["case_id"]
    trail: list[dict] = []
    with sqlite3.connect(db) as conn:
        row = conn.execute(
            "SELECT cluster_id FROM clusters WHERE case_id = ? ORDER BY cluster_id LIMIT 1",
            (cid,),
        ).fetchone()
    if row:
        trail = build_evidence_trail(db, cid, cluster_id=int(row[0]))
    errors = list(state.get("errors") or [])
    set_status(db, cid, "failed" if errors else "complete")
    return {"evidence_trail": trail, "timings": [_tick("explain", t0)]}


def build_graph() -> StateGraph:
    g = StateGraph(CaseState)
    g.add_node("ingest", node_ingest)
    g.add_node("evidence", node_evidence)
    g.add_node("stylometry", node_stylometry)
    g.add_node("fusion", node_fusion)
    g.add_node("graph", node_graph)
    g.add_node("opsec", node_opsec)
    g.add_node("explain", node_explain)
    g.add_edge(START, "ingest")
    g.add_edge("ingest", "evidence")
    g.add_edge("evidence", "stylometry")
    g.add_edge("evidence", "opsec")
    g.add_edge("stylometry", "fusion")
    g.add_edge("fusion", "graph")
    g.add_edge("graph", "explain")
    g.add_edge("opsec", "explain")
    g.add_edge("explain", END)
    return g


@contextmanager
def compiled_app(checkpoint_path: str | Path, *, interrupt_after: list[str] | None = None):
    """SqliteSaver.from_conn_string is a context manager (LangGraph 1.2.11)."""
    with SqliteSaver.from_conn_string(str(checkpoint_path)) as saver:
        g = build_graph()
        yield g.compile(checkpointer=saver, interrupt_after=interrupt_after or [])


def export_architecture_png(path: Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    compiled = build_graph().compile()
    g = compiled.get_graph()
    (path.parent / "architecture.mmd").write_text(g.draw_mermaid(), encoding="utf-8")
    try:
        png = g.draw_mermaid_png()
        path.write_bytes(png)
        return path
    except Exception:
        _render_graph_png(g, path)
        return path


def _render_graph_png(lg_graph, path: Path) -> None:
    """Local fallback when mermaid.ink is unreachable. Still from the compiled graph."""
    import matplotlib.pyplot as plt
    import networkx as nx

    g = nx.DiGraph()
    for src, dst in ((e.source, e.target) for e in lg_graph.edges):
        g.add_edge(src, dst)
    pos = nx.spring_layout(g, seed=0, k=1.8)
    fig, ax = plt.subplots(figsize=(10, 6), facecolor="#0a0e17")
    ax.set_facecolor("#0a0e17")
    nx.draw_networkx(
        g,
        pos,
        ax=ax,
        node_color="#1a2233",
        edge_color="#c9a227",
        font_color="#eef2f7",
        font_size=9,
        node_size=1800,
        arrows=True,
    )
    ax.axis("off")
    fig.savefig(path, dpi=140, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)


def invoke_pipeline(
    db_path: str | Path,
    case_id: str,
    *,
    config_path: str = "config.yaml",
    checkpoint_path: str | Path | None = None,
    thread_id: str | None = None,
    markets: list[str] | None = None,
    interrupt_after: list[str] | None = None,
    heuristic: bool = False,
) -> dict[str, Any]:
    ckpt = Path(checkpoint_path or Path(db_path).parent / f"{case_id}.ckpt.sqlite")
    thread_id = thread_id or case_id
    initial: CaseState = {
        "case_id": case_id,
        "db_path": str(db_path),
        "config_path": config_path,
        "markets": markets or [],
        "heuristic": heuristic,  # type: ignore[typeddict-item]
        "errors": [],
        "timings": [],
    }
    cfg = {"configurable": {"thread_id": thread_id}}
    with compiled_app(ckpt, interrupt_after=interrupt_after) as app:
        return app.invoke(initial, cfg)


def main(argv: list[str] | None = None) -> int:
    import argparse

    p = argparse.ArgumentParser(description="SUTRANETRA LangGraph wrapper (not the pipeline owner)")
    p.add_argument("--config", default="config.yaml")
    p.add_argument("--db", default=None)
    p.add_argument("--case-id", required=True)
    p.add_argument("--checkpoint", default=None)
    p.add_argument("--architecture", default="docs/architecture.png")
    args = p.parse_args(argv)
    with open(args.config, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    db = args.db or cfg["paths"]["sqlite_db"]
    export_architecture_png(Path(args.architecture))
    print("architecture", args.architecture)
    out = invoke_pipeline(
        db, args.case_id, config_path=args.config, checkpoint_path=args.checkpoint
    )
    print("case", out.get("case_id"), "scored", out.get("scored_pairs"), "errors", out.get("errors"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
