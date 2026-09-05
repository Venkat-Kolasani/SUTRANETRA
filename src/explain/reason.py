"""Template-first pair explanations (SPEC.md §14). Deterministic; no LLM."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from src.evidence.score import WEIGHT

FRAMING = (
    "Handles, wallets, and PGP fingerprints are pseudonymous identifiers. "
    "SUTRANETRA reports correlation confidence, not an identity verdict."
)

_KIND_SHARED = {
    "pgp_fpr": "Shared PGP fingerprint",
    "btc": "Shared BTC address",
    "xmr": "Shared XMR address",
    "onion": "Shared onion address",
    "clearnet": "Shared clearnet domain",
    "email": "Shared email",
}


def _open(db: sqlite3.Connection | str | Path) -> tuple[sqlite3.Connection, bool]:
    if isinstance(db, sqlite3.Connection):
        db.row_factory = sqlite3.Row
        return db, False
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    return conn, True


def _fmt(x: float, n: int = 2) -> str:
    return f"{float(x):.{n}f}"


def shorten(value: str, head: int = 6, tail: int = 4) -> str:
    s = str(value)
    if len(s) <= head + tail + 1:
        return s
    return f"{s[:head]}…{s[-tail:]}"


def template_sentence(ev: dict[str, Any]) -> str:
    """Render investigator prose from a structured evidence dict. Omits absent fields."""
    a, b = ev["a"], ev["b"]
    parts: list[str] = []
    parts.append(f"{_alias_clause(a)} and {_alias_clause(b)}")
    conf = ev.get("confidence")
    if conf is not None:
        parts[-1] += f" — confidence {_fmt(conf)}."
    else:
        parts[-1] += "."
    shown, omitted = _sentence_evidence(ev.get("shared_evidence") or [])
    for item in shown:
        kind = item.get("kind")
        value = item.get("value")
        if not kind or value in (None, ""):
            continue
        label = _KIND_SHARED.get(kind, f"Shared {kind}")
        bit = f"{label} `{shorten(str(value))}`"
        n = item.get("n_posts")
        if n is not None:
            bit += f" in {int(n)} post{'s' if int(n) != 1 else ''}"
        parts.append(bit + ".")
    if omitted:
        parts.append(f"Plus {omitted} additional shared hard-evidence values.")
    s_char = ev.get("s_char")
    if s_char is not None:
        parts.append(f"Stylometric similarity {_fmt(s_char)} (char n-gram).")
    s_time = ev.get("s_time")
    if s_time is not None:
        t = f"Posting-hour overlap {_fmt(s_time)}"
        tz = ev.get("timezone") or {}
        off = tz.get("shared_utc_offset")
        if off is not None:
            sign = "+" if off >= 0 else ""
            t += f", both consistent with UTC{sign}{int(off)}"
        parts.append(t + ".")
    return " ".join(parts)


def _sentence_evidence(items: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    """Sentence lists PGP + a couple of wallets; full list stays on the dict."""
    pgp = [x for x in items if x.get("kind") == "pgp_fpr"]
    wal = [x for x in items if x.get("kind") in ("btc", "xmr")]
    rest = [x for x in items if x.get("kind") not in ("pgp_fpr", "btc", "xmr")]
    shown = pgp + wal[:2]
    if not shown:
        shown = rest[:2]
    omitted = max(0, len(items) - len(shown))
    return shown, omitted


def _alias_clause(rec: dict[str, Any]) -> str:
    name = rec.get("alias")
    market = rec.get("market")
    n = rec.get("n_posts")
    if name in (None, "") or market in (None, ""):
        raise ValueError("alias and market are required")
    if n is None:
        return f"`{name}` ({market})"
    return f"`{name}` ({market}, {int(n)} posts)"


def explain_pair(
    db: sqlite3.Connection | str | Path,
    case_id: str,
    a_alias_id: int,
    b_alias_id: int,
) -> dict[str, Any]:
    """Load stored pair/evidence rows and return the Prompt 16 input dict."""
    conn, own = _open(db)
    try:
        ev = pair_evidence(conn, case_id, a_alias_id, b_alias_id)
        ev["template_sentence"] = template_sentence(ev)
        return ev
    finally:
        if own:
            conn.close()


def pair_evidence(
    conn: sqlite3.Connection, case_id: str, a_alias_id: int, b_alias_id: int
) -> dict[str, Any]:
    a = _alias(conn, a_alias_id)
    b = _alias(conn, b_alias_id)
    if a is None or b is None:
        raise ValueError("unknown alias_id")
    row = conn.execute(
        """
        SELECT * FROM pair_scores
        WHERE case_id = ?
          AND ((a_alias_id = ? AND b_alias_id = ?)
            OR (a_alias_id = ? AND b_alias_id = ?))
        """,
        (case_id, a_alias_id, b_alias_id, b_alias_id, a_alias_id),
    ).fetchone()
    shared = _shared_evidence(conn, a_alias_id, b_alias_id)
    tz = _timezone_both(conn, a_alias_id, b_alias_id)
    out: dict[str, Any] = {
        "case_id": case_id,
        "a": a,
        "b": b,
        "confidence": None if row is None else row["confidence"],
        "s_char": None if row is None else row["s_char"],
        "s_embed": None if row is None else row["s_embed"],
        "s_hard": None if row is None else row["s_hard"],
        "s_time": None if row is None else row["s_time"],
        "n_shared_hard": None if row is None else row["n_shared_hard"],
        "shared_evidence": shared,
        "timezone": tz,
        "framing": FRAMING,
        "system": "SUTRANETRA",
    }
    return out


def _alias(conn: sqlite3.Connection, alias_id: int) -> dict[str, Any] | None:
    r = conn.execute(
        "SELECT id AS alias_id, alias, market, n_posts FROM aliases WHERE id = ?",
        (alias_id,),
    ).fetchone()
    return dict(r) if r else None


def _shared_evidence(conn: sqlite3.Connection, a: int, b: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT e.kind, e.value,
               COUNT(DISTINCT e.post_id) AS n_posts,
               GROUP_CONCAT(e.id) AS evidence_ids
        FROM evidence e
        WHERE e.alias_id IN (?, ?)
        GROUP BY e.kind, e.value
        HAVING COUNT(DISTINCT e.alias_id) = 2
        """,
        (a, b),
    ).fetchall()
    items = []
    for r in rows:
        ids = [int(x) for x in str(r["evidence_ids"]).split(",") if x]
        items.append(
            {
                "kind": r["kind"],
                "value": r["value"],
                "n_posts": r["n_posts"],
                "evidence_ids": ids,
            }
        )
    items.sort(key=lambda x: (-WEIGHT.get(x["kind"], 0.0), x["kind"], x["value"]))
    return items


def _timezone_both(conn: sqlite3.Connection, a: int, b: int) -> dict[str, Any] | None:
    exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='alias_activity'"
    ).fetchone()
    if not exists:
        return None
    recs = {
        r["alias_id"]: r
        for r in conn.execute(
            """
            SELECT alias_id, tz_offset_hours, tz_confidence, n_ts
            FROM alias_activity WHERE alias_id IN (?, ?)
            """,
            (a, b),
        )
    }
    ra, rb = recs.get(a), recs.get(b)
    if ra is None or rb is None:
        return None
    oa, ob = ra["tz_offset_hours"], rb["tz_offset_hours"]
    if oa is None or ob is None:
        return None
    out: dict[str, Any] = {
        "a_utc_offset": oa,
        "b_utc_offset": ob,
        "a_tz_confidence": ra["tz_confidence"],
        "b_tz_confidence": rb["tz_confidence"],
    }
    if int(round(oa)) == int(round(ob)):
        out["shared_utc_offset"] = int(round(oa))
    return out


def main(argv: list[str] | None = None) -> int:
    import argparse

    import yaml

    p = argparse.ArgumentParser(description="SUTRANETRA template explanations")
    p.add_argument("--config", default="config.yaml")
    p.add_argument("--db", default=None)
    p.add_argument("--case-id", required=True)
    p.add_argument("--limit", type=int, default=5)
    args = p.parse_args(argv)
    with open(args.config, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    db = args.db or cfg["paths"]["sqlite_db"]
    conn, _ = _open(db)
    pairs = conn.execute(
        """
        SELECT a_alias_id, b_alias_id, confidence, n_shared_hard, s_time
        FROM pair_scores WHERE case_id = ?
        ORDER BY n_shared_hard DESC, confidence DESC
        LIMIT 20
        """,
        (args.case_id,),
    ).fetchall()
    shown = 0
    for r in pairs:
        ev = explain_pair(conn, args.case_id, r["a_alias_id"], r["b_alias_id"])
        print(ev["template_sentence"])
        print("  backing", {k: ev[k] for k in ("confidence", "s_char", "s_time", "n_shared_hard")})
        print("  shared", ev["shared_evidence"])
        shown += 1
        if shown >= args.limit:
            break
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
