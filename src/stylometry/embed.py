"""Topic/domain proximity via MiniLM embeddings (SPEC.md §8.2).

S_embed is a semantic/topic signal — same product category, same jargon —
not writing style. Char n-grams (S_char) carry style. Treating S_embed as
style is the first-draft failure mode (unrelated cannabis vendors matching
because they discuss cannabis).

Each post is hygiene-cleaned and alias-redacted with the Prompt 05 functions,
embedded on CPU (all-MiniLM-L6-v2, batch 64), then mean-pooled per alias.
S_embed(A, B) is cosine of those alias vectors.
"""

from __future__ import annotations

import random
import sqlite3
import time
from pathlib import Path

import numpy as np

from src.stylometry.hygiene import hygienize
from src.stylometry.redact import redact_aliases

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
MAX_POSTS = 200
BATCH = 64

PAIR_EMBED_SCHEMA = """
CREATE TABLE IF NOT EXISTS pair_channel_scores (
  a_alias_id INTEGER NOT NULL,
  b_alias_id INTEGER NOT NULL,
  s_embed REAL,
  s_time REAL,
  PRIMARY KEY (a_alias_id, b_alias_id)
);
"""


def load_model(name: str = MODEL_NAME):
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(name, device="cpu")


def embed_posts(model, texts: list[str], *, batch_size: int = BATCH) -> np.ndarray:
    if not texts:
        dim = getattr(model, "get_embedding_dimension", model.get_sentence_embedding_dimension)()
        return np.zeros((0, dim), dtype=np.float32)
    return model.encode(
        texts,
        batch_size=batch_size,
        show_progress_bar=False,
        convert_to_numpy=True,
        normalize_embeddings=True,
    )


def mean_pool(post_vecs: np.ndarray) -> np.ndarray:
    if post_vecs.size == 0:
        return post_vecs
    pooled = post_vecs.mean(axis=0)
    n = float(np.linalg.norm(pooled))
    if n == 0:
        return pooled.astype(np.float32)
    return (pooled / n).astype(np.float32)


def s_embed(vec_a: np.ndarray, vec_b: np.ndarray) -> float:
    """Cosine of two alias-level topic vectors. Not a style score."""
    if vec_a.size == 0 or vec_b.size == 0:
        return float("nan")
    return float(np.dot(vec_a, vec_b))


def _reservoir_add(
    buckets: dict[int, list[str]],
    counts: dict[int, int],
    rngs: dict[int, random.Random],
    alias_id: int,
    text: str,
    cap: int,
) -> None:
    counts[alias_id] = counts.get(alias_id, 0) + 1
    n = counts[alias_id]
    lst = buckets.setdefault(alias_id, [])
    if n <= cap:
        lst.append(text)
        return
    rng = rngs.get(alias_id)
    if rng is None:
        rng = random.Random(alias_id)
        rngs[alias_id] = rng
    j = rng.randrange(n)
    if j < cap:
        lst[j] = text


def collect_alias_posts(
    conn: sqlite3.Connection, *, cap: int = MAX_POSTS, redact: bool = True
) -> dict[int, list[str]]:
    names = {
        row["id"]: row["alias"]
        for row in conn.execute("SELECT id, alias FROM aliases")
    }
    buckets: dict[int, list[str]] = {}
    counts: dict[int, int] = {}
    rngs: dict[int, random.Random] = {}
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
        if redact:
            cleaned = redact_aliases(cleaned, names[row["alias_id"]])
        if cleaned:
            _reservoir_add(buckets, counts, rngs, row["alias_id"], cleaned, cap)
        if n % 100000 == 0:
            print(f"  hygienized {n} posts for embed …", flush=True)
    return buckets


def fit_alias_vectors(
    model,
    buckets: dict[int, list[str]],
    *,
    batch_size: int = BATCH,
) -> dict[int, np.ndarray]:
    dim = getattr(model, "get_embedding_dimension", model.get_sentence_embedding_dimension)()
    ids: list[int] = []
    texts: list[str] = []
    for aid, posts in buckets.items():
        for t in posts:
            ids.append(aid)
            texts.append(t)
    out_sum: dict[int, np.ndarray] = {}
    out_n: dict[int, int] = {}
    t0 = time.perf_counter()
    for start in range(0, len(texts), batch_size):
        chunk_ids = ids[start : start + batch_size]
        chunk = texts[start : start + batch_size]
        vecs = embed_posts(model, chunk, batch_size=batch_size)
        for aid, v in zip(chunk_ids, vecs):
            if aid not in out_sum:
                out_sum[aid] = np.zeros(dim, dtype=np.float64)
                out_n[aid] = 0
            out_sum[aid] += v
            out_n[aid] += 1
        done = start + len(chunk)
        if done % 20000 < batch_size:
            print(
                f"  embedded {done}/{len(texts)} posts "
                f"({time.perf_counter() - t0:.0f}s) …",
                flush=True,
            )
    out: dict[int, np.ndarray] = {}
    for aid, total in out_sum.items():
        pooled = total / out_n[aid]
        nrm = float(np.linalg.norm(pooled))
        out[aid] = (pooled / nrm).astype(np.float32) if nrm else pooled.astype(np.float32)
    return out


def pairwise_s_embed(
    vectors: dict[int, np.ndarray], pairs: list[tuple[int, int]]
) -> list[float]:
    scores = []
    for a, b in pairs:
        va, vb = vectors.get(a), vectors.get(b)
        if va is None or vb is None or va.size == 0 or vb.size == 0:
            scores.append(float("nan"))
            continue
        scores.append(s_embed(va, vb))
    return scores


def persist_s_embed(db_path: str | Path, pairs: list[tuple[int, int]], scores: list[float]) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.executescript(PAIR_EMBED_SCHEMA)
        rows = [
            (a, b, None if s != s else float(s))  # NaN → NULL
            for (a, b), s in zip(pairs, scores)
        ]
        sql = """
            INSERT INTO pair_channel_scores (a_alias_id, b_alias_id, s_embed, s_time)
            VALUES (?, ?, ?, NULL)
            ON CONFLICT (a_alias_id, b_alias_id) DO UPDATE SET s_embed = excluded.s_embed
            """
        for start in range(0, len(rows), 50_000):
            conn.executemany(sql, rows[start : start + 50_000])
            conn.commit()


def run(db_path: str | Path, stylometry: dict) -> dict:
    name = stylometry.get("embedding_model") or MODEL_NAME
    cap = int(stylometry.get("embed_max_posts", MAX_POSTS))
    batch = int(stylometry.get("embed_batch_size", BATCH))
    t0 = time.perf_counter()
    print(f"loading {name} on CPU …", flush=True)
    model = load_model(name)
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        print("collecting per-alias posts (hygiene+redact, cap %s) …" % cap, flush=True)
        buckets = collect_alias_posts(conn, cap=cap, redact=True)
        n_posts = sum(len(v) for v in buckets.values())
        print(f"  {len(buckets)} aliases, {n_posts} posts after cap", flush=True)
        print("encoding …", flush=True)
        vectors = fit_alias_vectors(model, buckets, batch_size=batch)
        pairs = [
            (r["a_alias_id"], r["b_alias_id"])
            for r in conn.execute(
                "SELECT a_alias_id, b_alias_id FROM char_candidates"
            )
        ]
    print(f"scoring S_embed on {len(pairs)} candidate pairs …", flush=True)
    scores = pairwise_s_embed(vectors, pairs)
    persist_s_embed(db_path, pairs, scores)
    elapsed = time.perf_counter() - t0
    return {
        "n_aliases_embedded": len(vectors),
        "n_posts_embedded": n_posts,
        "n_pairs": len(pairs),
        "elapsed_sec": elapsed,
        "model": name,
        "vectors": vectors,
    }


def main(argv: list[str] | None = None) -> int:
    import argparse

    import yaml

    parser = argparse.ArgumentParser(
        description="Topic embeddings (S_embed) — not a style signal"
    )
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--db", default=None)
    args = parser.parse_args(argv)
    with open(args.config, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    db_path = args.db or cfg["paths"]["sqlite_db"]
    summary = run(db_path, cfg.get("stylometry") or {})
    print("S_embed (topic/domain proximity, not style)")
    for k in (
        "model",
        "n_aliases_embedded",
        "n_posts_embedded",
        "n_pairs",
        "elapsed_sec",
    ):
        print(f"  {k}: {summary[k]}")
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """
            SELECT a.alias AS a, a.market AS a_m, b.alias AS b, b.market AS b_m,
                   c.s_char, p.s_embed
            FROM char_candidates c
            JOIN pair_channel_scores p
              ON p.a_alias_id = c.a_alias_id AND p.b_alias_id = c.b_alias_id
            JOIN aliases a ON a.id = c.a_alias_id
            JOIN aliases b ON b.id = c.b_alias_id
            WHERE a.alias = 'Jack N Hoff' AND b.alias = 'Jack N Hoff'
            """
        ).fetchone()
        if row:
            print(
                f"  Jack N Hoff {row['a_m']}/{row['b_m']} "
                f"s_char={row['s_char']} s_embed={row['s_embed']}"
            )
        diverged = conn.execute(
            """
            SELECT a.alias AS a, a.market AS a_m, b.alias AS b, b.market AS b_m,
                   c.s_char, p.s_embed
            FROM char_candidates c
            JOIN pair_channel_scores p
              ON p.a_alias_id = c.a_alias_id AND p.b_alias_id = c.b_alias_id
            JOIN aliases a ON a.id = c.a_alias_id
            JOIN aliases b ON b.id = c.b_alias_id
            WHERE p.s_embed IS NOT NULL AND c.s_char IS NOT NULL
              AND p.s_embed > 0.55 AND c.s_char < 0.12
            ORDER BY p.s_embed DESC
            LIMIT 5
            """
        ).fetchall()
        print("  topic-high / style-low corpus pairs:")
        for r in diverged:
            print(
                f"    {r['a']!r}@{r['a_m']} / {r['b']!r}@{r['b_m']} "
                f"s_embed={r['s_embed']:.3f} s_char={r['s_char']:.3f}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
