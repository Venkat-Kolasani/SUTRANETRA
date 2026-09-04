"""Cross-market ground-truth labels (SPEC.md §11.1–§11.3).

This module only emits (alias_a, market_a, alias_b, market_b, label, source)
tuples. It does not vectorize post text. Downstream stylometry (Prompts 05–06)
must redact both alias strings — and near-variants — before any feature is
computed. Feeding the handle that created a positive label into TF-IDF is a
blind-protocol leak, not a modelling choice.

Caveat (SPEC.md §11.3), state on stage before anyone asks: same handle across
markets is a labelling heuristic, not proof of identity. Handle-squatting and
post-Silk-Road-1 impersonation are documented. We use this label because it is
the best free ground truth in the corpus, and we say so.
"""

from __future__ import annotations

import itertools
import random
import sqlite3
from pathlib import Path

# Same-username cross-market positives are source='same_username'.
# Do not mix temporal-split weak positives into that source string.
LABEL_SCHEMA = """
CREATE TABLE IF NOT EXISTS label_pairs (
  a_alias_id INTEGER NOT NULL,
  b_alias_id INTEGER NOT NULL,
  a_market TEXT NOT NULL,
  a_alias TEXT NOT NULL,
  b_market TEXT NOT NULL,
  b_alias TEXT NOT NULL,
  label INTEGER NOT NULL,
  source TEXT NOT NULL,
  PRIMARY KEY (a_alias_id, b_alias_id)
);
CREATE INDEX IF NOT EXISTS idx_label_source ON label_pairs(source, label);
"""

INSERT_SQL = """
INSERT OR IGNORE INTO label_pairs (
  a_alias_id, b_alias_id, a_market, a_alias, b_market, b_alias, label, source
) VALUES (
  :a_alias_id, :b_alias_id, :a_market, :a_alias, :b_market, :b_alias, :label, :source
)
"""


def _order(row_a: sqlite3.Row, row_b: sqlite3.Row) -> tuple[sqlite3.Row, sqlite3.Row]:
    if (row_a["market"], row_a["alias"], row_a["id"]) <= (
        row_b["market"],
        row_b["alias"],
        row_b["id"],
    ):
        return row_a, row_b
    return row_b, row_a


def _payload(a: sqlite3.Row, b: sqlite3.Row, label: int, source: str) -> dict:
    a, b = _order(a, b)
    return {
        "a_alias_id": a["id"],
        "b_alias_id": b["id"],
        "a_market": a["market"],
        "a_alias": a["alias"],
        "b_market": b["market"],
        "b_alias": b["alias"],
        "label": label,
        "source": source,
    }


def _shared_evidence_pairs(conn: sqlite3.Connection) -> set[tuple[int, int]]:
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


def positive_pairs(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        "SELECT id, market, alias FROM aliases WHERE alias IS NOT NULL AND alias != ''"
    ).fetchall()
    by_name: dict[str, list] = {}
    for row in rows:
        by_name.setdefault(row["alias"], []).append(row)
    out = []
    for _name, occ in by_name.items():
        markets = {r["market"] for r in occ}
        if len(markets) < 2:
            continue
        for a, b in itertools.combinations(occ, 2):
            if a["market"] == b["market"]:
                continue
            out.append(_payload(a, b, 1, "same_username"))
    return out


def random_negatives(
    conn: sqlite3.Connection,
    n: int,
    banned: set[tuple[int, int]],
    rng: random.Random,
) -> list[dict]:
    rows = conn.execute(
        "SELECT id, market, alias FROM aliases WHERE alias IS NOT NULL AND alias != ''"
    ).fetchall()
    if len(rows) < 2:
        return []
    out = []
    seen: set[tuple[int, int]] = set()
    attempts = 0
    while len(out) < n and attempts < n * 50:
        attempts += 1
        a, b = rng.sample(rows, 2)
        if a["market"] == b["market"] or a["alias"] == b["alias"]:
            continue
        a, b = _order(a, b)
        key = (a["id"], b["id"])
        if key in banned or key in seen:
            continue
        seen.add(key)
        out.append(_payload(a, b, 0, "random_neg"))
    return out


def hard_negatives(
    conn: sqlite3.Connection,
    n: int,
    shared_ev: set[tuple[int, int]],
    banned: set[tuple[int, int]],
    rng: random.Random,
) -> list[dict]:
    """Same market, co-posted in a thread (topic proxy), no shared hard evidence."""
    by_key = {
        (r["market"], r["alias"]): r
        for r in conn.execute("SELECT id, market, alias FROM aliases")
    }
    threads = conn.execute(
            """
            SELECT market, thread_id, GROUP_CONCAT(alias, char(31)) AS aliases
            FROM (
              SELECT DISTINCT market, thread_id, alias
              FROM posts
              WHERE thread_id IS NOT NULL AND alias IS NOT NULL
            )
            GROUP BY market, thread_id
            HAVING COUNT(*) >= 2
            """
        ).fetchall()
    rng.shuffle(threads)
    out = []
    seen: set[tuple[int, int]] = set()
    for thread in threads:
        names = [x for x in (thread["aliases"] or "").split("\x1f") if x]
        rng.shuffle(names)
        found = False
        for na, nb in itertools.combinations(names, 2):
            ra = by_key.get((thread["market"], na))
            rb = by_key.get((thread["market"], nb))
            if ra is None or rb is None or ra["alias"] == rb["alias"]:
                continue
            ra, rb = _order(ra, rb)
            key = (ra["id"], rb["id"])
            if key in shared_ev or key in banned or key in seen:
                continue
            seen.add(key)
            out.append(_payload(ra, rb, 0, "hard_neg"))
            found = True
            break
        if found and len(out) >= n:
            break
    return out


def generate_labels(
    db_path: str | Path,
    *,
    seed: int = 0,
    neg_ratio: int = 1,
) -> dict:
    rng = random.Random(seed)
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        conn.executescript(LABEL_SCHEMA)
        conn.execute("DELETE FROM label_pairs")
        positives = positive_pairs(conn)
        banned = {(p["a_alias_id"], p["b_alias_id"]) for p in positives}
        n_pos = len(positives)
        n_neg = max(n_pos * neg_ratio, 0)
        shared_ev = _shared_evidence_pairs(conn)
        rands = random_negatives(conn, n_neg, banned, rng)
        banned |= {(p["a_alias_id"], p["b_alias_id"]) for p in rands}
        hards = hard_negatives(conn, n_neg, shared_ev, banned, rng)
        rows = positives + rands + hards
        conn.executemany(INSERT_SQL, rows)
        conn.commit()
        by_source = dict(
            conn.execute("SELECT source, COUNT(*) FROM label_pairs GROUP BY source")
        )
        n_markets = dict(
            conn.execute(
                """
                SELECT a_market || '|' || b_market AS span, COUNT(*)
                FROM label_pairs WHERE source = 'same_username'
                GROUP BY span ORDER BY 2 DESC
                """
            )
        )
    used_temporal = False
    return {
        "positives": by_source.get("same_username", 0),
        "random_neg": by_source.get("random_neg", 0),
        "hard_neg": by_source.get("hard_neg", 0),
        "temporal_split": by_source.get("temporal_split", 0),
        "market_spans": n_markets,
        "used_temporal_fallback": used_temporal,
        "total": sum(by_source.values()),
    }


def main(argv: list[str] | None = None) -> int:
    import argparse

    import yaml

    parser = argparse.ArgumentParser(description="Build cross-market label pairs")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--db", default=None)
    args = parser.parse_args(argv)
    with open(args.config, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    db_path = args.db or cfg["paths"]["sqlite_db"]
    summary = generate_labels(db_path)
    print("label_pairs")
    for k, v in summary.items():
        print(f"  {k}: {v}")
    if summary["positives"] < 30:
        print(
            "WARNING: positive count is thin for a 5-feature logistic fit; "
            "consider temporal-split fallback (not applied)."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
