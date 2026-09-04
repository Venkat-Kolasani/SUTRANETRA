"""Pair feature vectors for fusion (SPEC.md §10).

Observed channels plus log1p(n_shared_hard). Missing S_time is imputed to
the corpus mean and flagged with time_missing=1 — never replaced by 0.
"""

from __future__ import annotations

import math
import sqlite3
from collections import defaultdict

from src.evidence.score import s_hard as s_hard_score
from src.evidence.score import shared_items

FEATURE_NAMES = (
    "s_char",
    "s_embed",
    "s_hard",
    "s_time",
    "log1p_n_shared_hard",
    "time_missing",
)


def evidence_index(conn: sqlite3.Connection) -> dict[int, list[tuple[str, str]]]:
    idx: dict[int, list[tuple[str, str]]] = defaultdict(list)
    for aid, kind, value in conn.execute(
        "SELECT alias_id, kind, value FROM evidence WHERE alias_id IS NOT NULL"
    ):
        idx[aid].append((kind, value))
    return idx


def pair_hard(
    ev: dict[int, list[tuple[str, str]]], a: int, b: int
) -> tuple[float, int]:
    shared = shared_items(ev.get(a, []), ev.get(b, []))
    return s_hard_score(shared)


def impute_row(
    s_char: float | None,
    s_embed: float | None,
    s_hard: float,
    s_time: float | None,
    n_shared: int,
    means: dict[str, float],
) -> list[float]:
    time_missing = 1.0 if s_time is None else 0.0
    st = means["s_time"] if s_time is None else float(s_time)
    se = means["s_embed"] if s_embed is None else float(s_embed)
    sc = means["s_char"] if s_char is None else float(s_char)
    return [
        sc,
        se,
        float(s_hard),
        st,
        math.log1p(n_shared),
        time_missing,
    ]


def corpus_means(conn: sqlite3.Connection) -> dict[str, float]:
    def _avg(sql: str) -> float:
        v = conn.execute(sql).fetchone()[0]
        return float(v) if v is not None else 0.0

    return {
        "s_char": _avg("SELECT AVG(s_char) FROM char_candidates WHERE s_char IS NOT NULL"),
        "s_embed": _avg(
            "SELECT AVG(s_embed) FROM pair_channel_scores WHERE s_embed IS NOT NULL"
        ),
        "s_time": _avg(
            "SELECT AVG(s_time) FROM pair_channel_scores WHERE s_time IS NOT NULL"
        ),
    }
