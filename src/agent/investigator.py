"""Read-only investigator agent (SPEC.md §16.2). Phrases stored results; never scores."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import yaml
from langchain.agents import create_agent
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from src.agent.tools import make_tools
from src.graph.neo4j_sink import active_profile
from src.llm.client import get_chat_model, llm_block, llm_reachable, ollama_reachable

# Re-export for older UI/tests.
__all__ = ["ask", "ollama_reachable"]
log = logging.getLogger(__name__)


def _message_text(content: Any) -> str:
    if not content:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str) and block.strip():
                parts.append(block)
            elif isinstance(block, dict):
                if block.get("type") in (None, "text") and block.get("text"):
                    parts.append(str(block["text"]))
            elif getattr(block, "type", None) in (None, "text") and getattr(block, "text", None):
                parts.append(str(block.text))
        return "\n".join(parts).strip()
    return str(content).strip()

SYSTEM = """You are SUTRANETRA's investigator console.

You retrieve already-computed forensic results. You never decide whether two aliases
are the same person, never compute a new confidence, and never state an identity
verdict. Forbidden phrasing: "same person", "same operator", "identity", "guilty".
Say "stored cluster / stored confidence / shared identifier rows" instead.
Wallets, PGP fingerprints, and handles are pseudonymous identifiers.
A clearnet mention in a post is not ownership of that domain.

Tool routing (follow exactly):
- Shared PGP/wallet/onion with a named handle → search_evidence only
  (kind=pgp_fpr|btc|onion, value=handle or hex). List ONLY aliases in those rows.
  Do not call get_cluster for a shared-key question.
- Cluster membership / markets / shared_evidence → get_cluster
- Stored S_char/S_embed/S_hard/S_time/confidence → score_pair
- "evidence trail" / "walk me through" → evidence_trail only; narrate returned steps
- Case metadata → get_case
- "most records" / "highest post count" / "most active alias" → top_aliases
- Posting hours / timezone → alias_timeline
- Clearnet domain + "what else" / siblings / operator infrastructure →
  you MUST call search_evidence(kind=clearnet, value=the domain) AND
  ct_pivot(domain=the domain) before answering. Mentions ≠ ownership.
  ct_pivot siblings are certificate-sharing hostnames from cache, not a verdict.
- opsec_scan only for localhost demo URLs
- Graph topology (shortest path, 3+ markets, shared BTC) → cypher_query

Reply in 4–8 short sentences of prose (never a raw JSON array). Use market:alias
and evidence_id / alias_id from the tool output. Never invent handles.
If ct_pivot ran, sentence 1 must quote siblings[] and source exactly.
Cap: at most two tool rounds unless the clearnet chain above requires both tools.
"""


def _load_cfg(config_path: str | Path = "config.yaml") -> dict:
    with open(config_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _provenance_footer(traces: list[dict]) -> str:
    lines = []
    for tr in traces:
        name, out = tr.get("name"), tr.get("output")
        if name == "ct_pivot" and isinstance(out, dict):
            lines.append(
                f"Provenance · ct_pivot source={out.get('source')} siblings={out.get('siblings')}"
            )
        elif name == "search_evidence" and isinstance(out, dict):
            als = [f"{a.get('market')}:{a.get('alias')}" for a in (out.get("aliases") or [])[:8]]
            fp = None
            for row in out.get("sample") or []:
                if row.get("kind") == "pgp_fpr" and row.get("value"):
                    fp = row["value"]
                    break
            bit = f"Provenance · search_evidence n_aliases={out.get('n_aliases')} sample={als}"
            if fp:
                bit += f" pgp={fp}"
            lines.append(bit)
        elif name == "evidence_trail" and isinstance(out, list):
            lines.append("Provenance · evidence_trail " + " → ".join(s.get("type", "?") for s in out))
    return "\n".join(dict.fromkeys(lines))


def ask(
    question: str,
    *,
    db_path: str | Path,
    case_id: str,
    cfg: dict | None = None,
    config_path: str = "config.yaml",
) -> dict[str, Any]:
    """Run one investigator turn. Returns prose + tool provenance. No DB writes."""
    cfg = cfg or _load_cfg(config_path)
    settings = llm_block(cfg)
    if not llm_reachable(cfg):
        return {
            "ok": False,
            "degraded": True,
            "text": "",
            "tool_traces": [],
            "model": None,
        }
    profile_name, _block = active_profile(cfg)
    tools = make_tools(db_path, case_id, cfg)
    try:
        llm = get_chat_model(cfg)
        agent = create_agent(
            llm,
            tools,
            system_prompt=SYSTEM + f"\nActive case_id={case_id}. Config profile={profile_name}.",
            name="sutranetra-investigator",
        )
        result = agent.invoke(
            {"messages": [HumanMessage(content=question)]},
            {"recursion_limit": 6},
        )
    except Exception:
        log.exception("investigator ask failed")
        return {
            "ok": False,
            "degraded": True,
            "text": "",
            "tool_traces": [],
            "model": settings["model"],
        }
    messages = result.get("messages") or []
    traces = []
    pending: dict[str, dict] = {}
    text = ""
    for m in messages:
        if isinstance(m, AIMessage):
            chunk = _message_text(m.content)
            if chunk:
                text = chunk
            for call in m.tool_calls or []:
                pending[call["id"]] = {"name": call["name"], "args": call.get("args") or {}}
        elif isinstance(m, ToolMessage):
            rec = pending.get(m.tool_call_id) or {"name": m.name, "args": {}}
            raw = m.content
            try:
                parsed = json.loads(raw) if isinstance(raw, str) else raw
            except json.JSONDecodeError:
                parsed = raw
            rec["output"] = parsed
            traces.append(rec)
    footer = _provenance_footer(traces)
    if footer:
        text = (text.rstrip() + "\n\n" + footer) if text else footer
    return {
        "ok": True,
        "degraded": False,
        "text": text,
        "tool_traces": traces,
        "model": settings["model"],
        "case_id": case_id,
    }
