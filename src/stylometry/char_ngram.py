"""Character n-gram stylometry (SPEC.md §8.1).

Character 3–5-grams (word-boundary-aware) are the workhorse style channel:
punctuation habits, spacing quirks, casing, and typo patterns survive topic
change. That is what keeps this score from just rediscovering "both vendors
sell cannabis." Fit one TF-IDF on the whole corpus so cross-market cosine
is in the same space.

S_char(A, B) is cosine similarity of the two alias documents' TF-IDF vectors
(not the SVD used only for blocking).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import numpy as np
from scipy import sparse
from sklearn.feature_extraction.text import TfidfVectorizer

from src.stylometry.hygiene import hygienize
from src.stylometry.redact import redact_aliases

CHAR_CANDIDATE_SCHEMA = """
CREATE TABLE IF NOT EXISTS char_candidates (
  a_alias_id INTEGER NOT NULL,
  b_alias_id INTEGER NOT NULL,
  s_char REAL NOT NULL,
  in_neighbors INTEGER NOT NULL DEFAULT 0,
  in_hard_ev INTEGER NOT NULL DEFAULT 0,
  in_eval INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (a_alias_id, b_alias_id)
);
"""


def build_alias_documents(
    conn: sqlite3.Connection, *, redact: bool = True
) -> tuple[list[int], list[str], dict[int, str]]:
    """One concatenated document per alias_id. Always hygiene-clean.

    `redact=True` strips each alias's own handle from its document. That is
    mandatory anywhere a label exists (blind protocol) and is the default
    for the unlabeled path too — a signature handle is not writing style.
    """
    names = {
        row["id"]: row["alias"]
        for row in conn.execute("SELECT id, alias FROM aliases")
    }
    buckets: dict[int, list[str]] = {aid: [] for aid in names}
    cur = conn.execute(
        """
        SELECT a.id AS alias_id, p.raw_html, p.body
        FROM posts p
        JOIN aliases a ON a.market = p.market AND a.alias = p.alias
        """
    )
    n = 0
    for row in cur:
        n += 1
        cleaned = hygienize(row["raw_html"] or "", row["body"] or "")
        if cleaned:
            buckets[row["alias_id"]].append(cleaned)
        if n % 100000 == 0:
            print(f"  hygienized {n} posts …", flush=True)
    alias_ids = sorted(names)
    docs: list[str] = []
    for aid in alias_ids:
        text = "\n".join(buckets[aid])
        if redact:
            text = redact_aliases(text, names[aid])
        docs.append(text)
    return alias_ids, docs, names


def fit_char_tfidf(
    docs: list[str],
    *,
    min_df: int = 3,
    max_features: int = 200_000,
) -> tuple[TfidfVectorizer, sparse.spmatrix]:
    vec = TfidfVectorizer(
        analyzer="char_wb",
        ngram_range=(3, 5),
        min_df=min_df,
        max_features=max_features,
        sublinear_tf=True,
        lowercase=False,
    )
    x = vec.fit_transform(docs)
    return vec, x


def pairwise_s_char(
    x: sparse.spmatrix, row_a: np.ndarray, row_b: np.ndarray, *, batch: int = 8000
) -> np.ndarray:
    """Cosine on L2-normalised TF-IDF rows = row-wise sparse dot."""
    out = np.empty(len(row_a), dtype=np.float64)
    for start in range(0, len(row_a), batch):
        sl = slice(start, start + batch)
        a = x[row_a[sl]]
        b = x[row_b[sl]]
        out[sl] = np.asarray(a.multiply(b).sum(axis=1)).ravel()
    return out


_INSERT_CAND = """
INSERT INTO char_candidates (
  a_alias_id, b_alias_id, s_char, in_neighbors, in_hard_ev, in_eval
) VALUES (?, ?, ?, ?, ?, ?)
"""


def run(db_path: str | Path, stylometry: dict) -> dict:
    from src.stylometry.blocking import (
        eval_pairs,
        hard_evidence_pairs,
        neighbor_pairs,
        positive_eval_pairs,
        recall_report,
        reduce_for_index,
        union_candidates,
    )

    min_df = int(stylometry.get("char_ngram_min_df", 3))
    max_features = int(stylometry.get("char_ngram_max_features", 200_000))
    top_k = int(stylometry.get("blocking_top_k", 50))
    svd_dims = int(stylometry.get("blocking_svd_dims", 256))

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        n_alias = conn.execute("SELECT COUNT(*) FROM aliases").fetchone()[0]
        print(f"building alias documents ({n_alias} aliases) …", flush=True)
        alias_ids, docs, _names = build_alias_documents(conn, redact=True)
        print("fitting char TF-IDF …", flush=True)
        vec, x = fit_char_tfidf(docs, min_df=min_df, max_features=max_features)
        vocab = len(vec.vocabulary_)
        print(f"  vocabulary {vocab} (cap {max_features})", flush=True)
        print(f"TruncatedSVD → {svd_dims} then FAISS top-{top_k} …", flush=True)
        dense = reduce_for_index(x, svd_dims)
        neighbors = neighbor_pairs(dense, alias_ids, top_k)
        hard = hard_evidence_pairs(conn)
        labelled = eval_pairs(conn)
        positives = positive_eval_pairs(conn)
        candidates = union_candidates(neighbors, hard, labelled)
        recall = recall_report(positives, neighbors, candidates)
        print(
            f"  blocking recall_forced={recall['recall_forced']} "
            f"recall_neighbors_only={recall['recall_neighbors_only']} "
            f"union={len(candidates)} neighbors={len(neighbors)} hard={len(hard)}",
            flush=True,
        )
        id_to_row = {aid: i for i, aid in enumerate(alias_ids)}
        ordered = [p for p in candidates if p[0] in id_to_row and p[1] in id_to_row]
        # Exact TF-IDF cosine for neighbour + eval pairs (the fusion/eval
        # numbers). Shared marketplace onions inflate hard-evidence cliques to
        # tens of millions of pairs — those extras get SVD-space cosine.
        # ponytail: upgrade = sparse TF-IDF on the full union if you have the RAM/time.
        exact_pairs = [p for p in ordered if p in neighbors or p in labelled]
        approx_pairs = [p for p in ordered if p not in neighbors and p not in labelled]
        print(
            f"scoring S_char: {len(exact_pairs)} TF-IDF pairs "
            f"(full blocking union {len(ordered)}; "
            f"{len(approx_pairs)} hard-only onion/clearnet cliques not persisted)",
            flush=True,
        )

    print(f"writing {len(exact_pairs)} char_candidates (neighbors ∪ eval) …", flush=True)
    with sqlite3.connect(db_path) as out:
        out.executescript(CHAR_CANDIDATE_SCHEMA)
        out.execute("DELETE FROM char_candidates")
        if exact_pairs:
            ra = np.fromiter((id_to_row[a] for a, _ in exact_pairs), dtype=np.int64)
            rb = np.fromiter((id_to_row[b] for _, b in exact_pairs), dtype=np.int64)
            scores = pairwise_s_char(x, ra, rb)
            payload = [
                (
                    a,
                    b,
                    float(s),
                    int((a, b) in neighbors),
                    int((a, b) in hard),
                    int((a, b) in labelled),
                )
                for (a, b), s in zip(exact_pairs, scores)
            ]
            for start in range(0, len(payload), 50_000):
                out.executemany(_INSERT_CAND, payload[start : start + 50_000])
                out.commit()

    n_full = n_alias * (n_alias - 1) // 2
    return {
        "n_aliases": n_alias,
        "vocab_size": vocab,
        "max_features": max_features,
        "n_neighbor_pairs": len(neighbors),
        "n_hard_pairs": len(hard),
        "n_eval_pairs": len(labelled),
        "n_candidates": len(ordered),
        "n_full_pairs": n_full,
        **recall,
    }


def _lookup_pair(
    conn: sqlite3.Connection, alias: str, market_a: str, market_b: str
) -> tuple[int, int] | None:
    rows = conn.execute(
        "SELECT id, market FROM aliases WHERE alias = ?", (alias,)
    ).fetchall()
    by_m = {r["market"]: r["id"] for r in rows}
    if market_a in by_m and market_b in by_m:
        a, b = by_m[market_a], by_m[market_b]
        return (a, b) if a < b else (b, a)
    return None


def main(argv: list[str] | None = None) -> int:
    import argparse

    import yaml

    parser = argparse.ArgumentParser(description="Char n-gram stylometry + blocking")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--db", default=None)
    args = parser.parse_args(argv)
    with open(args.config, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    db_path = args.db or cfg["paths"]["sqlite_db"]
    summary = run(db_path, cfg.get("stylometry") or {})
    print("char n-gram + blocking")
    for k in (
        "n_aliases",
        "vocab_size",
        "max_features",
        "n_neighbor_pairs",
        "n_hard_pairs",
        "n_eval_pairs",
        "n_candidates",
        "n_full_pairs",
        "n_positives",
        "recall_forced",
        "recall_neighbors_only",
    ):
        print(f"  {k}: {summary[k]}")
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        similar = _lookup_pair(conn, "Jack N Hoff", "silkroad1", "silkroad2")
        dissimilar = conn.execute(
            """
            SELECT a_alias_id, b_alias_id, a_alias, b_alias
            FROM label_pairs WHERE source = 'random_neg' LIMIT 1
            """
        ).fetchone()
        if similar:
            s = conn.execute(
                "SELECT s_char FROM char_candidates WHERE a_alias_id=? AND b_alias_id=?",
                similar,
            ).fetchone()
            print(
                f"  s_char Jack N Hoff SR1/SR2: {None if s is None else s['s_char']}"
            )
        if dissimilar:
            key = (
                min(dissimilar["a_alias_id"], dissimilar["b_alias_id"]),
                max(dissimilar["a_alias_id"], dissimilar["b_alias_id"]),
            )
            s = conn.execute(
                "SELECT s_char FROM char_candidates WHERE a_alias_id=? AND b_alias_id=?",
                key,
            ).fetchone()
            print(
                f"  s_char random_neg {dissimilar['a_alias']!r}/"
                f"{dissimilar['b_alias']!r}: {None if s is None else s['s_char']}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

