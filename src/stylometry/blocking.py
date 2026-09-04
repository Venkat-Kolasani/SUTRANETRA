"""Candidate-pair blocking (SPEC.md §8.3).

50k aliases → ~1.25B pairs. Score only: top-k FAISS neighbours of SVD-reduced
char n-gram vectors, union hard-evidence pairs, union labelled eval pairs.

Report two recalls: with forced inclusion (demo number) and neighbours-only
(the production number).
"""

from __future__ import annotations

import itertools
import sqlite3

import faiss
import numpy as np
from scipy import sparse
from sklearn.decomposition import TruncatedSVD


def reduce_for_index(x: sparse.spmatrix, n_components: int = 256) -> np.ndarray:
    n_samples = x.shape[0]
    dims = min(n_components, max(1, n_samples - 1), x.shape[1])
    svd = TruncatedSVD(n_components=dims, random_state=0)
    dense = svd.fit_transform(x).astype(np.float32)
    faiss.normalize_L2(dense)
    return dense


def neighbor_pairs(
    dense: np.ndarray, alias_ids: list[int], top_k: int
) -> set[tuple[int, int]]:
    n = dense.shape[0]
    k = min(top_k + 1, n)
    index = faiss.IndexFlatIP(dense.shape[1])
    index.add(dense)
    _, nn = index.search(dense, k)
    out: set[tuple[int, int]] = set()
    for i, nbrs in enumerate(nn):
        ai = alias_ids[i]
        for j in nbrs:
            j = int(j)
            if j < 0 or j == i:
                continue
            aj = alias_ids[j]
            if ai == aj:
                continue
            out.add((ai, aj) if ai < aj else (aj, ai))
    return out


def hard_evidence_pairs(conn: sqlite3.Connection) -> set[tuple[int, int]]:
    inv: dict[tuple[str, str], set[int]] = {}
    for alias_id, kind, value in conn.execute(
        "SELECT alias_id, kind, value FROM evidence WHERE alias_id IS NOT NULL"
    ):
        inv.setdefault((kind, value), set()).add(alias_id)
    shared: set[tuple[int, int]] = set()
    for ids in inv.values():
        ordered = sorted(ids)
        for a, b in itertools.combinations(ordered, 2):
            shared.add((a, b))
    return shared


def eval_pairs(conn: sqlite3.Connection) -> set[tuple[int, int]]:
    try:
        rows = conn.execute(
            "SELECT a_alias_id, b_alias_id FROM label_pairs"
        ).fetchall()
    except sqlite3.OperationalError:
        return set()
    return {(min(a, b), max(a, b)) for a, b in rows}


def positive_eval_pairs(conn: sqlite3.Connection) -> set[tuple[int, int]]:
    try:
        rows = conn.execute(
            "SELECT a_alias_id, b_alias_id FROM label_pairs WHERE label = 1"
        ).fetchall()
    except sqlite3.OperationalError:
        return set()
    return {(min(a, b), max(a, b)) for a, b in rows}


def union_candidates(
    neighbors: set[tuple[int, int]],
    hard: set[tuple[int, int]],
    labelled: set[tuple[int, int]],
) -> set[tuple[int, int]]:
    return neighbors | hard | labelled


def recall_report(
    positives: set[tuple[int, int]],
    neighbors: set[tuple[int, int]],
    candidates: set[tuple[int, int]],
) -> dict[str, float | int]:
    n_pos = len(positives)
    if n_pos == 0:
        return {
            "n_positives": 0,
            "recall_forced": 0.0,
            "recall_neighbors_only": 0.0,
        }
    return {
        "n_positives": n_pos,
        "recall_forced": len(positives & candidates) / n_pos,
        "recall_neighbors_only": len(positives & neighbors) / n_pos,
    }
