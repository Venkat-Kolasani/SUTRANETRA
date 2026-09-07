"""One chat model per profile. Cloud = Groq; local = Groq (API) or Ollama."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen

from src.graph.neo4j_sink import active_profile

OLLAMA_TAGS = "http://127.0.0.1:11434/api/tags"
_ENV_LOADED = False


def load_envfile() -> None:
    """Load repo `.env` into os.environ without overwriting a real export. No extra dep."""
    global _ENV_LOADED
    if _ENV_LOADED:
        return
    _ENV_LOADED = True
    # pytest must not inherit a developer's GROQ/.env or polish tests lie.
    if os.environ.get("SUTRANETRA_SKIP_DOTENV") == "1":
        return
    import sys

    if "pytest" in sys.modules:
        return
    seen: set[Path] = set()
    for root in (Path.cwd(), Path(__file__).resolve().parents[2]):
        path = (root / ".env").resolve()
        if path in seen or not path.is_file():
            continue
        seen.add(path)
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key, val = key.strip(), val.strip().strip("'").strip('"')
            if key and key not in os.environ:
                os.environ[key] = val


load_envfile()


def llm_block(cfg: dict, profile: str | None = None) -> dict[str, Any]:
    load_envfile()
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
    flag = os.environ.get("SUTRANETRA_LLM_ENABLED")
    if flag == "0":
        enabled = False
    elif flag == "1":
        enabled = True
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
