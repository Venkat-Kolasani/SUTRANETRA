"""Hidden-service leak detectors (SPEC.md §12.1). Localhost demo target only."""

from __future__ import annotations

import json
import re
import socket
import sqlite3
import ssl
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

from src.evidence.onion import extract_contacts
from src.pipeline.case import get_case

SERVER_AT_RE = re.compile(r"Server at\s+(\S+)", re.I)
GIT_URL_RE = re.compile(r'url\s*=\s*(\S+)', re.I)
INDEX_RE = re.compile(r"Index of\s+/", re.I)
DEFAULT_MARKERS = ("Welcome to nginx!", "It works!", "Apache2 Ubuntu Default Page")
ALLOWED_SCAN_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


def validate_scan_target(url: str) -> str:
    """Reject non-localhost scan targets (UI + CLI guard)."""
    parsed = urlparse(url.strip())
    if parsed.scheme not in ("http", "https"):
        raise ValueError("Only http/https targets are allowed.")
    host = (parsed.hostname or "").lower()
    if host not in ALLOWED_SCAN_HOSTS:
        raise ValueError("OpSec scans are limited to localhost demo targets (127.0.0.1 / localhost).")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    return f"{parsed.scheme}://{host}:{port}"


class _RefParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.refs: list[str] = []

    def handle_starttag(self, tag, attrs) -> None:
        d = dict(attrs)
        for k in ("src", "href"):
            if k in d and d[k]:
                self.refs.append(d[k])


def _get(url: str, timeout: float = 5.0, context=None):
    req = Request(url, headers={"User-Agent": "SUTRANETRA-opsec-scanner/0.1"})
    try:
        with urlopen(req, timeout=timeout, context=context) as resp:
            body = resp.read()
            headers = {k.lower(): v for k, v in resp.headers.items()}
            return resp.status, headers, body
    except HTTPError as e:
        body = e.read() if e.fp else b""
        headers = {k.lower(): v for k, v in (e.headers.items() if e.headers else [])}
        return e.code, headers, body
    except URLError:
        raise


def _host_from_url(ref: str, base: str) -> str | None:
    absu = urljoin(base, ref)
    p = urlparse(absu)
    host = (p.hostname or "").lower()
    if not host or host.endswith(".onion") or host in {"localhost", "127.0.0.1"}:
        return None
    if p.scheme not in ("http", "https"):
        return None
    if host.startswith("www."):
        host = host[4:]
    return host


def detect_clearnet_refs(html: str, base: str) -> list[dict]:
    parser = _RefParser()
    parser.feed(html)
    out, seen = [], set()
    for ref in parser.refs:
        host = _host_from_url(ref, base)
        if host and host not in seen:
            seen.add(host)
            out.append(
                {
                    "finding_kind": "clearnet_ref",
                    "value": host,
                    "detail": ref,
                }
            )
    return out


def scan_http(base: str) -> list[dict]:
    base = base.rstrip("/")
    findings: list[dict] = []
    status, headers, body = _get(base + "/")
    html = body.decode("utf-8", "replace")
    findings.extend(detect_clearnet_refs(html, base + "/"))
    if "server" in headers:
        findings.append({"finding_kind": "server_header", "value": headers["server"], "detail": "/"})
    if "x-powered-by" in headers:
        findings.append(
            {"finding_kind": "x_powered_by", "value": headers["x-powered-by"], "detail": "/"}
        )

    st, _, sb = _get(base + "/server-status")
    text = sb.decode("utf-8", "replace")
    if st == 200:
        m = SERVER_AT_RE.search(text)
        findings.append(
            {
                "finding_kind": "server_status",
                "value": m.group(1) if m else "reachable",
                "detail": text[:400],
            }
        )

    st, _, sb = _get(base + "/.git/config")
    if st == 200:
        m = GIT_URL_RE.search(sb.decode("utf-8", "replace"))
        findings.append(
            {
                "finding_kind": "git_config",
                "value": m.group(1) if m else "reachable",
                "detail": sb.decode("utf-8", "replace")[:400],
            }
        )

    for path, kind in (
        ("/.env", "env_leak"),
        ("/backup.zip", "backup_leak"),
        ("/config.php.bak", "config_bak"),
    ):
        st, _, sb = _get(base + path)
        if st == 200 and sb:
            findings.append(
                {
                    "finding_kind": kind,
                    "value": path,
                    "detail": f"status=200 bytes={len(sb)}",
                }
            )

    st, _, sb = _get(base + "/files/")
    listing = sb.decode("utf-8", "replace")
    if st == 200 and INDEX_RE.search(listing):
        findings.append(
            {"finding_kind": "dir_listing", "value": "/files/", "detail": listing[:300]}
        )

    st, _, sb = _get(base + "/it-works")
    page = sb.decode("utf-8", "replace")
    if st == 200 and any(m in page for m in DEFAULT_MARKERS):
        findings.append(
            {"finding_kind": "default_page", "value": "/it-works", "detail": page.strip()[:80]}
        )
    return findings


def scan_tls(url: str) -> list[dict]:
    import subprocess

    parsed = urlparse(url)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 443
    ctx = ssl._create_unverified_context()
    with socket.create_connection((host, port), timeout=5) as raw:
        with ctx.wrap_socket(raw, server_hostname=host) as sock:
            der = sock.getpeercert(binary_form=True)
    pem = ssl.DER_cert_to_PEM_cert(der)
    text = subprocess.check_output(
        ["openssl", "x509", "-noout", "-text"],
        input=pem.encode(),
        timeout=5,
    ).decode()
    names = re.findall(r"DNS:([^,\s]+)", text)
    clear = [
        n.lower()
        for n in names
        if not n.lower().endswith(".onion") and n.lower() not in {"localhost"}
    ]
    if not clear:
        return []
    return [
        {
            "finding_kind": "tls_san",
            "value": ",".join(clear),
            "detail": "supporting detector, not the demo headline",
        }
    ]


def scan_target(http_url: str, tls_url: str | None = None) -> list[dict]:
    out = scan_http(http_url)
    if tls_url:
        try:
            out.extend(scan_tls(tls_url))
        except OSError:
            pass
    return out


def scan_corpus(conn: sqlite3.Connection, limit: int = 50) -> list[dict]:
    rows = conn.execute(
        """
        SELECT p.id, p.market, p.msg_id, p.alias, p.body, p.source_archive,
               p.scrape_date, p.source_member_path, p.content_sha256
        FROM posts p
        WHERE p.body LIKE '%***clearnet***%' OR p.body LIKE '%***CLEARNET***%'
           OR p.body LIKE '%***ClearNet***%'
        LIMIT ?
        """,
        (limit,),
    )
    findings = []
    seen = set()
    for r in rows:
        for hit in extract_contacts(r["body"]):
            if hit["kind"] != "clearnet":
                continue
            key = (hit["value"], r["id"])
            if key in seen:
                continue
            seen.add(key)
            findings.append(
                {
                    "finding_kind": "corpus_clearnet",
                    "value": hit["value"],
                    "detail": json.dumps(
                        {
                            "market": r["market"],
                            "msg_id": r["msg_id"],
                            "alias": r["alias"],
                            "source_archive": r["source_archive"],
                            "scrape_date": r["scrape_date"],
                            "source_member_path": r["source_member_path"],
                            "content_sha256": r["content_sha256"],
                            "context": hit["context"][:240],
                        }
                    ),
                }
            )
    return findings


def persist_findings(db_path: str | Path, case_id: str, target: str, findings: list[dict]) -> int:
    if get_case(db_path, case_id) is None:
        raise ValueError(f"unknown case {case_id}")
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with sqlite3.connect(db_path) as conn:
        conn.executemany(
            """
            INSERT INTO opsec_findings (case_id, target, finding_kind, value, detail, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                (case_id, target, f["finding_kind"], f["value"], f.get("detail") or "", now)
                for f in findings
            ],
        )
        conn.commit()
    return len(findings)


def list_findings(db_path: str | Path, case_id: str) -> list[dict]:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        return [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM opsec_findings WHERE case_id = ? ORDER BY id",
                (case_id,),
            )
        ]


def main(argv: list[str] | None = None) -> int:
    import argparse

    import yaml

    p = argparse.ArgumentParser(description="OpSec leak scanner (localhost demo / corpus)")
    p.add_argument("--config", default="config.yaml")
    p.add_argument("--db", default=None)
    p.add_argument("--case-id", required=True)
    p.add_argument("--target", default=None, help="http://127.0.0.1:8080")
    p.add_argument("--tls-target", default=None)
    p.add_argument("--corpus", action="store_true")
    p.add_argument("--start-demo", action="store_true")
    args = p.parse_args(argv)
    with open(args.config, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    db = args.db or cfg["paths"]["sqlite_db"]
    stop = None
    target = args.target
    tls = args.tls_target
    if args.start_demo:
        from src.opsec.demo_target.serve import serve_in_thread

        info = serve_in_thread()
        stop = info["stop"]
        target = info["http"]
        tls = info["https"]
        print("demo_target", target, tls)
    findings: list[dict] = []
    if target:
        findings.extend(scan_target(target, tls))
        persist_findings(db, args.case_id, target, findings)
    if args.corpus:
        with sqlite3.connect(db) as conn:
            conn.row_factory = sqlite3.Row
            corp = scan_corpus(conn)
        persist_findings(db, args.case_id, "corpus", corp)
        findings = findings + corp
    print("opsec_findings", len(findings))
    for f in findings:
        print(f"  {f['finding_kind']}: {f['value']}")
    if stop:
        stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
