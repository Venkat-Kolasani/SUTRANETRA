"""HTTP client used by Streamlit in cloud profile."""

from __future__ import annotations

import os
from typing import Any

import requests
import yaml

from src.graph.neo4j_sink import active_profile


def load_config(path: str = "config.yaml") -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def api_base(cfg: dict | None = None) -> str:
    env = os.environ.get("SUTRANETRA_API_URL", "").strip().rstrip("/")
    if not env:
        try:
            import streamlit as st

            env = str(st.secrets.get("SUTRANETRA_API_URL", "") or "").strip().rstrip("/")
        except Exception:
            env = ""
    if env:
        return env
    cfg = cfg or load_config()
    _, block = active_profile(cfg)
    return str(block.get("api_base_url") or "").strip().rstrip("/")


def is_remote(cfg: dict | None = None) -> bool:
    return bool(api_base(cfg))


def get(path: str, cfg: dict | None = None, **params: Any) -> Any:
    url = api_base(cfg) + path
    r = requests.get(url, params={k: v for k, v in params.items() if v is not None}, timeout=120)
    r.raise_for_status()
    return r.json()


def post(path: str, json_body: dict, cfg: dict | None = None) -> Any:
    url = api_base(cfg) + path
    r = requests.post(url, json=json_body, timeout=180)
    r.raise_for_status()
    return r.json()


def get_bytes(path: str, cfg: dict | None = None) -> bytes:
    url = api_base(cfg) + path
    r = requests.get(url, timeout=300)
    r.raise_for_status()
    return r.content
