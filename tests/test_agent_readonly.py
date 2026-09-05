"""Agent tools hold SQLite mode=ro; writes raise."""

from __future__ import annotations

import ast
import sqlite3
from pathlib import Path

import pytest

from src.agent.tools import TOOL_NAMES, make_tools, open_ro
from src.ingest.schema import init_db

ROOT = Path(__file__).resolve().parents[1]


def test_open_ro_write_raises(tmp_path: Path):
    db = tmp_path / "ro.sqlite"
    init_db(db)
    conn = open_ro(db)
    with pytest.raises(sqlite3.OperationalError):
        conn.execute("CREATE TABLE should_fail (x INTEGER)")
        conn.commit()


def test_every_tool_calls_open_ro():
    path = ROOT / "src" / "agent" / "tools.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    tool_fns = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        decos = []
        for d in node.decorator_list:
            if isinstance(d, ast.Name):
                decos.append(d.id)
            elif isinstance(d, ast.Call) and isinstance(d.func, ast.Name):
                decos.append(d.func.id)
        if "tool" in decos:
            called = [
                n.func.id
                for n in ast.walk(node)
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
            ]
            tool_fns[node.name] = called
    missing = [n for n in TOOL_NAMES if n not in tool_fns]
    assert not missing, missing
    no_ro = [n for n, calls in tool_fns.items() if "open_ro" not in calls]
    assert not no_ro, f"tools that never call open_ro: {no_ro}"


def test_make_tools_names_and_ro(tmp_path: Path):
    db = tmp_path / "t.sqlite"
    init_db(db)
    tools = {t.name: t for t in make_tools(db, "CASE-X", {"paths": {"ct_cache": str(tmp_path)}})}
    assert set(tools) == set(TOOL_NAMES)
    conn = open_ro(db)
    with pytest.raises(sqlite3.OperationalError):
        conn.execute("INSERT INTO aliases (market, alias) VALUES ('x','y')")
        conn.commit()
