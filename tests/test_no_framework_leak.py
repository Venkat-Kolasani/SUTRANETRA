"""Nothing outside pipeline/ and agent/ may import langchain/langgraph.

Nothing outside graph/neo4j_sink.py and agent/ may import neo4j (SPEC.md §993).
"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "src"
ALLOWED = ("pipeline", "agent", "llm")
BANNED = frozenset(
    {
        "langchain",
        "langchain_core",
        "langchain_ollama",
        "langchain_groq",
        "langgraph",
        "langgraph.checkpoint",
        "langgraph.graph",
        "langgraph.checkpoint.sqlite",
    }
)
NEO4J_ALLOWED = {
    Path("graph") / "neo4j_sink.py",
}


def _imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module.split(".")[0])
    return names


def test_no_framework_leak_outside_pipeline_and_agent():
    leaks = []
    neo_leaks = []
    for path in ROOT.rglob("*.py"):
        rel = path.relative_to(ROOT)
        names = _imports(path)
        if rel.parts[0] not in ALLOWED:
            for name in names:
                if name in BANNED or name.startswith("langchain") or name.startswith("langgraph"):
                    leaks.append(f"{rel}: {name}")
        if rel.parts[0] != "agent" and rel not in NEO4J_ALLOWED:
            if "neo4j" in names:
                neo_leaks.append(str(rel))
    assert not leaks, "framework leaked outside src/pipeline, src/agent, src/llm:\n" + "\n".join(leaks)
    assert not neo_leaks, "neo4j leaked outside src/graph/neo4j_sink.py and src/agent/:\n" + "\n".join(
        neo_leaks
    )
