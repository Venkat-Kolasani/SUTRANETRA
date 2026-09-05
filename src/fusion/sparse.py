"""Sparse-evidence gate for fused confidence (SPEC.md §11.4).

An alias with fewer than SPARSE_MIN_POSTS posts must never produce a
forced high-confidence link. Cap confidence and emit reason =
"insufficient data" so the pair-level output matches the Prompt 06
low-post-count rule (temporal NULL under 20 timestamps), extended to
fusion generally.
"""

from __future__ import annotations

SPARSE_MIN_POSTS = 10
# Ceiling is intentionally low and below the demo link threshold (0.83).
SPARSE_CONF_CEILING = 0.35
REASON_INSUFFICIENT = "insufficient data"


def is_sparse(n_posts_a: int | None, n_posts_b: int | None) -> bool:
    na = 0 if n_posts_a is None else int(n_posts_a)
    nb = 0 if n_posts_b is None else int(n_posts_b)
    return na < SPARSE_MIN_POSTS or nb < SPARSE_MIN_POSTS


def apply_sparse_gate(
    confidence: float,
    n_posts_a: int | None,
    n_posts_b: int | None,
) -> tuple[float, str | None]:
    """Return (possibly capped confidence, reason or None)."""
    if not is_sparse(n_posts_a, n_posts_b):
        return float(confidence), None
    return min(float(confidence), SPARSE_CONF_CEILING), REASON_INSUFFICIENT
