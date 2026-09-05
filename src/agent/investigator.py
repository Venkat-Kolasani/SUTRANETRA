"""Read-only investigator agent (SPEC.md §16.2). Phrases stored results; never scores."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen

import yaml
from langchain.agents import create_agent
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_ollama import ChatOllama

from src.agent.tools import make_tools
from src.graph.neo4j_sink import active_profile

OLLAMA_TAGS = "http://127.0.0.1:11434/api/tags"
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


def resolve_model(cfg: dict) -> str:
    wanted = cfg.get("llm_model") or "qwen2.5:7b"
    names = ollama_models()
    if wanted in names or f"{wanted}:latest" in names:
        return wanted
    if any(n.startswith(wanted) for n in names):
        return next(n for n in names if n.startswith(wanted))
    # ponytail: 3B is weaker at tool choice; use only if the configured weights are absent.
    for fallback in ("qwen2.5:7b", "qwen2.5:latest", "llama3.2:latest", "llama3.2"):
        if fallback in names:
            return fallback
    return wanted


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
    if not ollama_reachable():
        return {
            "ok": False,
            "degraded": True,
            "text": "Ollama is unreachable. Use Search, Clusters, Pair inspector, and Evidence Trail.",
            "tool_traces": [],
            "model": None,
        }
    model_name = resolve_model(cfg)
    profile_name, _block = active_profile(cfg)
    tools = make_tools(db_path, case_id, cfg)
    llm = ChatOllama(model=model_name, temperature=0)
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
    messages = result.get("messages") or []
    traces = []
    pending: dict[str, dict] = {}
    text = ""
    for m in messages:
        if isinstance(m, AIMessage):
            if m.content:
                text = m.content if isinstance(m.content, str) else str(m.content)
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
        "model": model_name,
        "case_id": case_id,
    }
