"""Nothing outside pipeline/ and agent/ may import langchain/langgraph."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "src"
ALLOWED = ("pipeline", "agent")
BANNED = frozenset(
    {
        "langchain",
        "langchain_core",
        "langchain_ollama",
        "langgraph",
        "langgraph.checkpoint",
        "langgraph.graph",
        "langgraph.checkpoint.sqlite",
    }
)


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
    for path in ROOT.rglob("*.py"):
        rel = path.relative_to(ROOT)
        if rel.parts[0] in ALLOWED:
            continue
        for name in _imports(path):
            if name in BANNED or name.startswith("langchain") or name.startswith("langgraph"):
                leaks.append(f"{rel}: {name}")
    assert not leaks, "framework leaked outside src/pipeline and src/agent:\n" + "\n".join(leaks)
