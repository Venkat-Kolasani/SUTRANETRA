"""Saturating shared-evidence score (SPEC.md §7.4)."""

from __future__ import annotations

WEIGHT = {
    "pgp_fpr": 3.0,
    "btc": 2.0,
    "xmr": 2.0,
    "onion": 1.0,
    "clearnet": 1.0,
    "email": 1.0,
}


def s_hard(shared: list[tuple[str, str]]) -> tuple[float, int]:
    """Return (S_hard, n_shared_hard) for shared (kind, value) pairs.

    S_hard = 1 - 0.5^k_weighted. One shared PGP fingerprint → 1 - 0.5^3 = 0.875.
    """
    k = 0.0
    for kind, _value in shared:
        k += WEIGHT.get(kind, 0.0)
    n = len(shared)
    if k == 0:
        return 0.0, n
    return 1.0 - (0.5**k), n


def shared_items(
    a: list[tuple[str, str]],
    b: list[tuple[str, str]],
) -> list[tuple[str, str]]:
    return sorted(set(a) & set(b))
