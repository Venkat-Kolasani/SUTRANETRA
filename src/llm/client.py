"""One chat model per profile. Cloud = Groq; local demo = Ollama."""

from __future__ import annotations

import json
import os
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen

from src.graph.neo4j_sink import active_profile

OLLAMA_TAGS = "http://127.0.0.1:11434/api/tags"


def llm_block(cfg: dict, profile: str | None = None) -> dict[str, Any]:
    name, block = active_profile(cfg, profile)
    llm = dict(block.get("llm") or {})
    provider = (
        os.environ.get("SUTRANETRA_LLM_PROVIDER")
        or llm.get("provider")
        or "ollama"
    )
    model = (
        os.environ.get("SUTRANETRA_LLM_MODEL")
        or llm.get("model")
        or cfg.get("llm_model")
        or "llama-3.3-70b-versatile"
    )
    enabled = bool(llm.get("enabled"))
    if os.environ.get("SUTRANETRA_LLM_ENABLED") == "0":
        enabled = False
    return {
        "profile": name,
        "enabled": enabled,
        "provider": str(provider).lower(),
        "model": model,
    }


def ollama_reachable(timeout: float = 1.5) -> bool:
    try:
        with urlopen(OLLAMA_TAGS, timeout=timeout) as resp:
            return 200 <= resp.status < 300
    except (URLError, TimeoutError, OSError):
        return False


def ollama_models() -> list[str]:
    try:
        with urlopen(OLLAMA_TAGS, timeout=2) as resp:
            data = json.loads(resp.read().decode())
        return [m.get("name") or m.get("model") for m in data.get("models") or [] if m]
    except (URLError, TimeoutError, OSError, json.JSONDecodeError):
        return []


def resolve_ollama_model(wanted: str) -> str:
    names = ollama_models()
    if wanted in names or f"{wanted}:latest" in names:
        return wanted
    if any(n.startswith(wanted) for n in names):
        return next(n for n in names if n.startswith(wanted))
    for fallback in ("qwen2.5:7b", "qwen2.5:latest", "llama3.2:latest", "llama3.2"):
        if fallback in names:
            return fallback
    return wanted


def llm_reachable(cfg: dict, profile: str | None = None) -> bool:
    s = llm_block(cfg, profile)
    if not s["enabled"]:
        return False
    if s["provider"] == "groq":
        return bool(os.environ.get("GROQ_API_KEY", "").strip())
    return ollama_reachable()


def get_chat_model(cfg: dict, profile: str | None = None):
    """Return a LangChain chat model. Caller handles missing deps / failures."""
    s = llm_block(cfg, profile)
    if s["provider"] == "groq":
        from langchain_groq import ChatGroq

        key = os.environ.get("GROQ_API_KEY", "").strip()
        if not key:
            raise RuntimeError("GROQ_API_KEY missing")
        return ChatGroq(model=s["model"], temperature=0, api_key=key)
    from langchain_ollama import ChatOllama

    return ChatOllama(model=resolve_ollama_model(s["model"]), temperature=0)
