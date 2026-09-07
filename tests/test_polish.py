"""Prompt 16: polish takes a structured dict; unreachable LLM → exact template."""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

from src.explain.reason import template_sentence
from src.llm.client import llm_block
from src.llm.polish import polish_explanation

ROOT = Path(__file__).resolve().parents[1]

EV = {
    "a": {"alias": "nihilist23", "market": "silkroad1", "n_posts": 2},
    "b": {"alias": "nxxxxxxx23", "market": "silkroad1", "n_posts": 1},
    "confidence": 0.8194,
    "s_char": 0.470,
    "s_embed": 0.474,
    "s_hard": 0.875,
    "s_time": None,
    "n_shared_hard": 1,
    "shared_evidence": [
        {
            "kind": "pgp_fpr",
            "value": "0551E07ABB21CA0F02FBFBECE8ED5F45C33DD26D",
            "n_posts": 3,
        }
    ],
    "timezone": {},
    "framing": "Handles are pseudonymous identifiers.",
    "system": "SUTRANETRA",
}

DEMO_CFG = {
    "profile": "demo",
    "llm_model": "qwen2.5:7b",
    "profiles": {
        "demo": {
            "neo4j": {"enabled": False},
            "llm": {"enabled": True, "provider": "ollama", "model": "qwen2.5:7b"},
        }
    },
}


def test_unreachable_llm_returns_exact_template(monkeypatch):
    monkeypatch.setattr("src.llm.client.OLLAMA_TAGS", "http://127.0.0.1:1/api/tags")
    out = polish_explanation(EV, DEMO_CFG)
    expected = template_sentence(EV)
    assert out == expected
    assert out != ""
    assert "nihilist23" in out


def test_llm_exception_returns_exact_template(monkeypatch):
    monkeypatch.setattr("src.llm.polish.llm_reachable", lambda cfg, profile=None: True)

    def boom(cfg, profile=None):
        raise ConnectionError("ollama down")

    monkeypatch.setattr("src.llm.polish.get_chat_model", boom)
    out = polish_explanation(EV, DEMO_CFG)
    assert out == template_sentence(EV)


def test_signature_is_structured_dict_only():
    sig = inspect.signature(polish_explanation)
    params = list(sig.parameters)
    assert params == ["evidence", "cfg"]
    assert "dict" in str(sig.parameters["evidence"].annotation)
    src = (ROOT / "src/llm/polish.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    imported = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module)
    assert "src.ingest" not in imported
    assert not any(m == "ingest" or m.startswith("src.ingest") for m in imported)
    assert "sqlite3" not in imported


def test_env_enable_switches_dev_to_groq(monkeypatch):
    monkeypatch.setenv("SUTRANETRA_LLM_ENABLED", "1")
    monkeypatch.setenv("SUTRANETRA_LLM_PROVIDER", "groq")
    monkeypatch.setenv("SUTRANETRA_LLM_MODEL", "llama-3.3-70b-versatile")
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test")
    cfg = {
        "profile": "dev",
        "profiles": {
            "dev": {
                "neo4j": {"enabled": False},
                "llm": {
                    "enabled": False,
                    "provider": "groq",
                    "model": "llama-3.3-70b-versatile",
                },
            }
        },
    }
    block = llm_block(cfg, "dev")
    assert block["enabled"] is True
    assert block["provider"] == "groq"
    assert block["model"] == "llama-3.3-70b-versatile"


def test_shares_llm_model_with_investigator():
    polish = (ROOT / "src/llm/polish.py").read_text(encoding="utf-8")
    agent = (ROOT / "src/agent/investigator.py").read_text(encoding="utf-8")
    assert "get_chat_model" in polish
    assert "get_chat_model" in agent
    assert "ChatOllama(" not in polish
    demo = llm_block(DEMO_CFG, "demo")
    assert demo["model"] == "qwen2.5:7b"
    assert demo["provider"] == "ollama"
