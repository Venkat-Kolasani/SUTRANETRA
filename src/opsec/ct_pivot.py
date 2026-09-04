"""Certificate Transparency pivot (SPEC.md §12.2). Cache-first; --live is opt-in."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

CERTSPOTTER = "https://api.certspotter.com/v1/issuances"
CRTSH = "https://crt.sh/"


def cache_id(kind: str, query: str) -> str:
    return hashlib.sha256(f"{kind}|{query}".encode()).hexdigest()


def cache_path(cache_dir: Path, kind: str, query: str) -> Path:
    return Path(cache_dir) / f"{cache_id(kind, query)}.json"


def _http_json(url: str, headers: dict | None = None, timeout: int = 30):
    req = Request(url, headers=headers or {"User-Agent": "SUTRANETRA-ct-pivot/0.1"})
    with urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def _normalize_issuances(raw) -> list[dict]:
    if isinstance(raw, dict) and "issuances" in raw:
        raw = raw["issuances"]
    if not isinstance(raw, list):
        return []
    out = []
    for row in raw:
        if not isinstance(row, dict):
            continue
        names = row.get("dns_names") or []
        if not names and row.get("name_value"):
            names = [n.strip() for n in str(row["name_value"]).split("\n") if n.strip()]
        issuer = row.get("issuer") or {}
        pubkey = row.get("pubkey_sha256") or issuer.get("pubkey_sha256")
        out.append(
            {
                "id": row.get("id"),
                "dns_names": [n.lower().rstrip(".") for n in names if n],
                "pubkey_sha256": pubkey,
                "issuer": issuer,
                "cert_sha256": row.get("cert_sha256") or row.get("tbs_sha256"),
            }
        )
    return out


def load_cached(cache_dir: Path, kind: str, query: str) -> list[dict] | None:
    p = cache_path(cache_dir, kind, query)
    if not p.exists():
        return None
    return _normalize_issuances(json.loads(p.read_text(encoding="utf-8")))


def save_cache(cache_dir: Path, kind: str, query: str, payload) -> Path:
    Path(cache_dir).mkdir(parents=True, exist_ok=True)
    p = cache_path(cache_dir, kind, query)
    p.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return p


def fetch_certspotter(domain: str, token: str | None = None) -> list:
    q = urlencode(
        {
            "domain": domain,
            "include_subdomains": "true",
            "expand": "dns_names",
        }
    )
    # second expand
    url = f"{CERTSPOTTER}?{q}&expand=issuer"
    headers = {"User-Agent": "SUTRANETRA-ct-pivot/0.1"}
    tok = token or os.environ.get("CERTSPOTTER_API_TOKEN") or os.environ.get("CERTSPOTTER_TOKEN")
    if tok:
        headers["Authorization"] = f"Bearer {tok}"
    return _http_json(url, headers=headers)


def fetch_crtsh(domain: str) -> list:
    q = urlencode({"q": domain, "output": "json"})
    return _http_json(f"{CRTSH}?{q}")


def issuances_for_domain(
    domain: str,
    cache_dir: Path,
    *,
    live: bool = False,
    token: str | None = None,
) -> tuple[list[dict], str]:
    domain = domain.lower().strip(".")
    query = f"domain={domain}&include_subdomains=true&expand=dns_names&expand=issuer"
    if not live:
        cached = load_cached(cache_dir, "certspotter", query)
        if cached is not None:
            return cached, "cache"
        return [], "cache_miss"
    try:
        raw = fetch_certspotter(domain, token=token)
        save_cache(cache_dir, "certspotter", query, raw)
        return _normalize_issuances(raw), "certspotter"
    except Exception:
        raw = fetch_crtsh(domain)
        save_cache(cache_dir, "certspotter", query, raw)
        return _normalize_issuances(raw), "crtsh"


def sibling_domains(issuances: list[dict], seed: str) -> set[str]:
    seed = seed.lower().strip(".")
    www = f"www.{seed}" if not seed.startswith("www.") else seed[4:]
    skip = {seed, f"www.{seed}", www, "*." + seed}
    out: set[str] = set()
    for iss in issuances:
        for n in iss.get("dns_names") or []:
            n = n.lower().rstrip(".")
            if n.startswith("*."):
                n = n[2:]
            if n and n not in skip and not n.endswith(".onion"):
                out.add(n)
    return out


def pubkeys(issuances: list[dict]) -> set[str]:
    return {i["pubkey_sha256"] for i in issuances if i.get("pubkey_sha256")}


def pivot(
    domain: str,
    cache_dir: Path,
    *,
    live: bool = False,
    token: str | None = None,
    recurse: bool = True,
    max_siblings: int = 8,
) -> dict:
    """Domain → cert dns_names → siblings; optional one-level recurse. pubkey grouped."""
    seed_iss, src = issuances_for_domain(domain, cache_dir, live=live, token=token)
    sibs = sibling_domains(seed_iss, domain)
    keys = pubkeys(seed_iss)
    same_key: set[str] = set()
    for iss in seed_iss:
        if iss.get("pubkey_sha256") in keys:
            same_key.update(iss.get("dns_names") or [])
    hop2: set[str] = set()
    hop_sources: dict[str, str] = {}
    if recurse:
        for sib in sorted(sibs)[:max_siblings]:
            iss2, src2 = issuances_for_domain(sib, cache_dir, live=live, token=token)
            hop_sources[sib] = src2
            hop2.update(sibling_domains(iss2, sib))
            hop2.update(sibling_domains(iss2, domain))
    hop2.discard(domain.lower())
    return {
        "domain": domain,
        "source": src,
        "n_issuances": len(seed_iss),
        "siblings": sorted(sibs),
        "pubkey_sha256": sorted(keys),
        "same_key_names": sorted({n.lower().rstrip(".") for n in same_key if n}),
        "recurse_siblings": sorted(hop2 - sibs),
        "hop_sources": hop_sources,
        "cache_file": str(cache_path(
            cache_dir,
            "certspotter",
            f"domain={domain.lower().strip('.')}&include_subdomains=true&expand=dns_names&expand=issuer",
        )),
    }


def main(argv: list[str] | None = None) -> int:
    import argparse

    import yaml

    from src.pipeline.case import get_case

    p = argparse.ArgumentParser(description="CT pivot (cache-first)")
    p.add_argument("--domain", required=True)
    p.add_argument("--config", default="config.yaml")
    p.add_argument("--cache-dir", default=None)
    p.add_argument("--live", action="store_true")
    p.add_argument("--case-id", default=None)
    p.add_argument("--db", default=None)
    args = p.parse_args(argv)
    with open(args.config, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    cache_dir = Path(args.cache_dir or cfg["paths"]["ct_cache"])
    token = (cfg.get("opsec") or {}).get("certspotter_token")
    result = pivot(args.domain, cache_dir, live=args.live, token=token)
    print(json.dumps(result, indent=2))
    if args.case_id:
        from src.opsec.scanner import persist_findings

        db = args.db or cfg["paths"]["sqlite_db"]
        if get_case(db, args.case_id) is None:
            raise SystemExit(f"unknown case {args.case_id}")
        findings = [
            {"finding_kind": "ct_sibling", "value": s, "detail": json.dumps({"seed": args.domain, "source": result["source"]})}
            for s in result["siblings"][:20]
        ]
        persist_findings(db, args.case_id, f"ct:{args.domain}", findings)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
