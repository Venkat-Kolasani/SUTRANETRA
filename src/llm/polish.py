"""Prompt 16: rewrite a structured evidence dict. Never sees posts or a DB."""

from __future__ import annotations

import json
from typing import Any

from src.explain.reason import template_sentence
from src.llm.client import get_chat_model, llm_reachable

_POLISH_SYSTEM = (
    "Rewrite the JSON facts into one natural investigator paragraph. "
    "Do not add facts, numbers, aliases, wallets, or domains that are not in the JSON. "
    "Do not change confidence. Do not issue an identity verdict. "
    "Keep the framing that handles are pseudonymous identifiers."
)


def polish_explanation(evidence: dict[str, Any], cfg: dict | None = None) -> str:
    """Only input is the Prompt 10 structured dict. Falls back to the template."""
    fallback = template_sentence(evidence)
    if not cfg or not llm_reachable(cfg):
        return fallback
    payload = {
        k: v
        for k, v in evidence.items()
        if k not in ("template_sentence",)
    }
    try:
        llm = get_chat_model(cfg)
        msg = llm.invoke(
            [
                ("system", _POLISH_SYSTEM),
                ("human", json.dumps(payload, default=str)),
            ]
        )
        text = msg.content if isinstance(msg.content, str) else str(msg.content)
        text = (text or "").strip()
        return text or fallback
    except Exception:
        return fallback
