"""Prompt 12 edge-case gates: hard-negative below threshold; sparse ceiling."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import numpy as np
import pytest

from src.fusion.model import fit_model, patch_sparse_reasons
from src.fusion.sparse import (
    REASON_INSUFFICIENT,
    SPARSE_CONF_CEILING,
    SPARSE_MIN_POSTS,
    apply_sparse_gate,
)
from src.ingest.schema import init_db

LINK_THRESHOLD = 0.83


def test_sparse_gate_enforced_not_coincidental():
    """Any pair involving an alias with <10 posts is capped + reasoned."""
    # Would-be high confidence must still drop.
    capped, reason = apply_sparse_gate(0.95, 3, 200)
    assert reason == REASON_INSUFFICIENT
    assert capped == SPARSE_CONF_CEILING
    assert capped < LINK_THRESHOLD

    capped2, reason2 = apply_sparse_gate(0.12, 9, 9)
    assert reason2 == REASON_INSUFFICIENT
    assert capped2 == 0.12  # already under ceiling

    ok, reason3 = apply_sparse_gate(0.91, 10, 10)
    assert reason3 is None
    assert ok == 0.91

    # Model path cannot bypass the gate: flush-style application.
    for raw in (0.5, 0.83, 0.99, 1.0):
        out, why = apply_sparse_gate(raw, SPARSE_MIN_POSTS - 1, 50)
        assert why == REASON_INSUFFICIENT
        assert out <= SPARSE_CONF_CEILING


def test_hard_negative_topic_high_hard_zero_below_threshold():
    """Synthetic hard-neg: high topic, no hard evidence → below link threshold."""
    rng = np.random.RandomState(1)
    n0, n1 = 300, 150
    x0 = rng.rand(n0, 6) * 0.3
    x0[:, 2] = 0.0
    x0[:, 4] = 0.0
    x0[:, 1] = 0.5 + 0.4 * rng.rand(n0)  # topic-ish negatives
    x1 = rng.rand(n1, 6) * 0.25
    x1[:, 2] = 0.875
    x1[:, 4] = np.log1p(1.0)
    x = np.vstack([x0, x1])
    y = np.array([0] * n0 + [1] * n1)
    clf = fit_model(x, y)
    # Mirrors CaliforniaCannabis/domesticdoode: high S_embed, S_hard=0.
    hard_neg = np.array([[0.33, 0.82, 0.0, 0.25, 0.0, 0.0]])
    p = float(clf.predict_proba(hard_neg)[0, 1])
    assert p < LINK_THRESHOLD, p


def test_patch_sparse_reasons_writes_ceiling(tmp_path: Path):
    db = tmp_path / "t.sqlite"
    init_db(db)
    with sqlite3.connect(db) as conn:
        conn.execute(
            "INSERT INTO cases (case_id, created_at, corpus_snapshot, config_hash, "
            "model_version, threshold, status) VALUES (?,?,?,?,?,?,?)",
            ("C1", "t", "{}", "h", "m", 0.83, "complete"),
        )
        conn.execute(
            "INSERT INTO aliases (id, market, alias, n_posts) VALUES (1,'m','thin',4)"
        )
        conn.execute(
            "INSERT INTO aliases (id, market, alias, n_posts) VALUES (2,'m','fat',40)"
        )
        conn.execute(
            "INSERT INTO pair_scores "
            "(case_id, a_alias_id, b_alias_id, confidence, n_shared_hard) "
            "VALUES ('C1', 1, 2, 0.91, 1)"
        )
        conn.commit()
    n = patch_sparse_reasons(db, "C1")
    assert n == 1
    with sqlite3.connect(db) as conn:
        conf, reason = conn.execute(
            "SELECT confidence, reason FROM pair_scores WHERE case_id='C1'"
        ).fetchone()
    assert conf == pytest.approx(SPARSE_CONF_CEILING)
    assert reason == REASON_INSUFFICIENT
