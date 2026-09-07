"""Thin read-only HTTP wrapper. Scoring stays in the CLI pipeline."""

from __future__ import annotations

import os
from pathlib import Path

import yaml
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel, Field

from src.agent.investigator import ask
from src.agent.tools import open_ro
from src.api import queries as q
from src.export.writers import write_clusters_csv, write_report_json, write_report_pdf
from src.graph.neo4j_sink import active_profile
from src.llm.client import llm_block, llm_reachable
from src.llm.polish import polish_explanation

app = FastAPI(
    title="SUTRANETRA",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/openapi.json",
)
STATIC = Path(__file__).resolve().parent / "static"


def _cfg() -> dict:
    path = os.environ.get("SUTRANETRA_CONFIG", "config.yaml")
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _db_path(cfg: dict) -> str:
    override = os.environ.get("SUTRANETRA_SQLITE")
    if override:
        return override
    name, block = active_profile(cfg)
    if name == "cloud" and Path("data/demo/attrib.sqlite").exists():
        return "data/demo/attrib.sqlite"
    return cfg["paths"]["sqlite_db"]


def _cors() -> list[str]:
    raw = os.environ.get("SUTRANETRA_CORS_ORIGINS", "*")
    return [x.strip() for x in raw.split(",") if x.strip()]


app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors(),
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


class ChatBody(BaseModel):
    case_id: str
    question: str


class PolishBody(BaseModel):
    evidence: dict = Field(..., description="Prompt 10 structured evidence dict only")


@app.api_route("/", methods=["GET", "HEAD"], include_in_schema=False)
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/docs", include_in_schema=False)
def docs_redirect():
    return RedirectResponse("/", status_code=307)


@app.get("/health")
def health():
    cfg = _cfg()
    name, _ = active_profile(cfg)
    db = _db_path(cfg)
    llm = llm_block(cfg)
    return {
        "ok": True,
        "profile": name,
        "db_exists": Path(db).exists(),
        "llm": {
            "enabled": llm["enabled"],
            "provider": llm["provider"],
            "model": llm["model"],
            "reachable": llm_reachable(cfg),
        },
    }


@app.get("/cases")
def cases():
    cfg = _cfg()
    conn = open_ro(_db_path(cfg))
    try:
        return q.json_safe(q.list_cases(conn))
    finally:
        conn.close()


@app.get("/cases/{case_id}")
def case_one(case_id: str):
    row = q.case_row(_db_path(_cfg()), case_id)
    if not row:
        raise HTTPException(404, "unknown case")
    return q.json_safe(row)


@app.get("/cases/{case_id}/search")
def search(case_id: str, q_text: str = Query("", alias="q")):
    cfg = _cfg()
    conn = open_ro(_db_path(cfg))
    try:
        return q.json_safe(q.search_payload(conn, q_text))
    finally:
        conn.close()


@app.get("/cases/{case_id}/clusters")
def clusters(case_id: str):
    cfg = _cfg()
    conn = open_ro(_db_path(cfg))
    try:
        return q.json_safe(q.clusters_payload(conn, case_id))
    finally:
        conn.close()


@app.get("/cases/{case_id}/clusters/{cluster_id}")
def cluster_one(case_id: str, cluster_id: int):
    cfg = _cfg()
    db = _db_path(cfg)
    case = q.case_row(db, case_id) or {}
    conn = open_ro(db)
    try:
        return q.json_safe(
            q.cluster_payload(conn, case_id, cluster_id, float(case.get("threshold") or 0.83))
        )
    finally:
        conn.close()


@app.get("/cases/{case_id}/aliases")
def aliases(case_id: str):
    cfg = _cfg()
    conn = open_ro(_db_path(cfg))
    try:
        return q.json_safe(q.alias_options(conn, case_id))
    finally:
        conn.close()


@app.get("/cases/{case_id}/pairs")
def pairs(
    case_id: str,
    a_alias_id: int,
    b_alias_id: int,
    polish: bool = False,
):
    cfg = _cfg()
    conn = open_ro(_db_path(cfg))
    try:
        return q.json_safe(
            q.pair_payload(conn, case_id, a_alias_id, b_alias_id, cfg, polish=polish)
        )
    finally:
        conn.close()


@app.get("/cases/{case_id}/trail")
def trail(
    case_id: str,
    cluster_id: int | None = None,
    a_alias_id: int | None = None,
    b_alias_id: int | None = None,
):
    cfg = _cfg()
    conn = open_ro(_db_path(cfg))
    try:
        return q.json_safe(
            q.trail_payload(
                conn,
                case_id,
                cluster_id=cluster_id,
                a_alias_id=a_alias_id,
                b_alias_id=b_alias_id,
            )
        )
    finally:
        conn.close()


@app.get("/cases/{case_id}/opsec")
def opsec(case_id: str):
    return q.json_safe(q.opsec_payload(_db_path(_cfg()), case_id))


@app.post("/agent/chat")
def agent_chat(body: ChatBody):
    cfg = _cfg()
    return ask(body.question, db_path=_db_path(cfg), case_id=body.case_id, cfg=cfg)


@app.post("/explain/polish")
def explain_polish(body: PolishBody):
    return {"sentence": polish_explanation(body.evidence, _cfg())}


def _export_candidates(case: dict, out_dir: Path, kind: str) -> list[Path]:
    stable = {
        "csv": out_dir / "clusters.csv",
        "json": out_dir / "report.json",
        "pdf": out_dir / "report.pdf",
    }[kind]
    legacy = {
        "csv": out_dir / "api_clusters.csv",
        "json": out_dir / "api_report.json",
        "pdf": out_dir / "api_report.pdf",
    }[kind]
    candidates = [stable, legacy]
    if kind == "pdf":
        candidates.extend((out_dir / "trail_report.pdf", out_dir / "dod_verify" / "report.pdf"))
        if case.get("report_path") and Path(case["report_path"]).suffix.lower() == ".pdf":
            candidates.append(Path(case["report_path"]))
    return candidates


def _fresh_export(path: Path, db_path: str) -> bool:
    try:
        return path.is_file() and path.stat().st_mtime_ns >= Path(db_path).stat().st_mtime_ns
    except OSError:
        return False


@app.get("/cases/{case_id}/exports")
def export_status(case_id: str):
    cfg = _cfg()
    db = _db_path(cfg)
    case = q.case_row(db, case_id)
    if not case:
        raise HTTPException(404, "unknown case")
    out_dir = Path("data/exports") / case_id
    result = {}
    for kind in ("csv", "json", "pdf"):
        path = next((p for p in _export_candidates(case, out_dir, kind) if _fresh_export(p, db)), None)
        result[kind] = {
            "ready": path is not None,
            "bytes": path.stat().st_size if path else 0,
        }
    return result


@app.get("/cases/{case_id}/export/{kind}")
def export_case(case_id: str, kind: str):
    cfg = _cfg()
    db = _db_path(cfg)
    case = q.case_row(db, case_id)
    if not case:
        raise HTTPException(404, "unknown case")
    out_dir = Path("data/exports") / case_id
    out_dir.mkdir(parents=True, exist_ok=True)
    if kind not in ("csv", "json", "pdf"):
        raise HTTPException(404, "kind must be csv|json|pdf")
    path = next((p for p in _export_candidates(case, out_dir, kind) if _fresh_export(p, db)), None)
    if path is None:
        path = out_dir / {"csv": "clusters.csv", "json": "report.json", "pdf": "report.pdf"}[kind]
        if kind == "csv":
            write_clusters_csv(db, case_id, path)
        elif kind == "json":
            write_report_json(db, case_id, path)
        else:
            write_report_pdf(db, case_id, path)
    media = {"csv": "text/csv", "json": "application/json", "pdf": "application/pdf"}[kind]
    filename = {"csv": "clusters.csv", "json": "report.json", "pdf": "report.pdf"}[kind]
    return FileResponse(path, media_type=media, filename=filename)
