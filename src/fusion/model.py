"""Learned fusion confidence (SPEC.md §10).

LogisticRegression on alias-disjoint labelled pairs. Output is predict_proba
(calibrated logistic probability), not a raw margin. --heuristic is a fallback
with fixed weights and must be labelled as such wherever it is reported.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

import joblib
import numpy as np
from sklearn.linear_model import LogisticRegression

from src.fusion.evaluate import metrics, save_confusion, save_pr_curve
from src.fusion.features import (
    FEATURE_NAMES,
    corpus_means,
    evidence_index,
    impute_row,
    pair_hard,
)
from src.ingest.schema import init_db
from src.pipeline.case import create_case, get_case, set_status

HEURISTIC_WEIGHTS = np.array([0.25, 0.10, 0.45, 0.20])  # char, embed, hard, time
MODEL_DIR = Path("data/models")


def alias_disjoint_split(
    rows: list[dict], *, seed: int = 0, test_frac: float = 0.3
) -> tuple[list[dict], list[dict], set[int], set[int]]:
    """Split by handle string so a person cannot appear on both sides.

    Same-username positives share one handle across two alias_ids; grouping
    by handle keeps that pair intact and still yields empty alias_id overlap.
    """
    rng = np.random.RandomState(seed)
    handles = sorted({r["a_alias"].lower() for r in rows} | {r["b_alias"].lower() for r in rows})
    rng.shuffle(handles)
    n_test = max(1, int(len(handles) * test_frac))
    test_h = set(handles[:n_test])
    train_h = set(handles[n_test:])
    train, test = [], []
    for r in rows:
        ha, hb = r["a_alias"].lower(), r["b_alias"].lower()
        in_tr = ha in train_h and hb in train_h
        in_te = ha in test_h and hb in test_h
        if in_tr:
            train.append(r)
        elif in_te:
            test.append(r)
    train_ids = {r["a_alias_id"] for r in train} | {r["b_alias_id"] for r in train}
    test_ids = {r["a_alias_id"] for r in test} | {r["b_alias_id"] for r in test}
    return train, test, train_ids, test_ids


def heuristic_confidence(x: np.ndarray) -> np.ndarray:
    """Fallback: clip(w · [S_char, S_embed, S_hard, S_time]). Not the default."""
    return np.clip(x[:, :4] @ HEURISTIC_WEIGHTS, 0.0, 1.0)


def fit_model(x: np.ndarray, y: np.ndarray) -> LogisticRegression:
    clf = LogisticRegression(
        class_weight="balanced", C=1.0, max_iter=1000, solver="lbfgs"
    )
    clf.fit(x, y)
    return clf


def persist_model(clf: LogisticRegression, means: dict, path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({"clf": clf, "means": means, "feature_names": list(FEATURE_NAMES)}, path)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()[:8]
    return f"fusion-v1@{digest}"


def _load_labeled_features(conn: sqlite3.Connection, means: dict, ev) -> list[dict]:
    labeled = conn.execute(
        """
        SELECT lp.a_alias_id, lp.b_alias_id, lp.a_alias, lp.b_alias, lp.label,
               c.s_char, p.s_embed, p.s_time
        FROM label_pairs lp
        LEFT JOIN char_candidates c
          ON c.a_alias_id = lp.a_alias_id AND c.b_alias_id = lp.b_alias_id
        LEFT JOIN pair_channel_scores p
          ON p.a_alias_id = lp.a_alias_id AND p.b_alias_id = lp.b_alias_id
        """
    ).fetchall()
    out = []
    for r in labeled:
        sh, n = pair_hard(ev, r["a_alias_id"], r["b_alias_id"])
        x = impute_row(r["s_char"], r["s_embed"], sh, r["s_time"], n, means)
        out.append(
            {
                "a_alias_id": r["a_alias_id"],
                "b_alias_id": r["b_alias_id"],
                "a_alias": r["a_alias"],
                "b_alias": r["b_alias"],
                "label": r["label"],
                "x": x,
                "s_char": r["s_char"],
                "s_embed": r["s_embed"],
                "s_hard": sh,
                "s_time": r["s_time"],
                "n_shared_hard": n,
            }
        )
    return out


def _flush(conn, insert, case_id, xs, meta, labels, predict_fn) -> int:
    x = np.asarray(xs, dtype=np.float64)
    conf = predict_fn(x)
    rows = []
    for (r, sh, ns), c in zip(meta, conf):
        key = (r["a_alias_id"], r["b_alias_id"])
        rows.append(
            (
                case_id,
                r["a_alias_id"],
                r["b_alias_id"],
                r["s_char"],
                r["s_embed"],
                sh,
                r["s_time"],
                ns,
                float(c),
                labels.get(key),
            )
        )
    conn.executemany(insert, rows)
    return len(rows)


def score_candidates(
    conn: sqlite3.Connection,
    case_id: str,
    predict_fn,
    means: dict,
    ev,
) -> int:
    cur = conn.execute(
        """
        SELECT c.a_alias_id, c.b_alias_id, c.s_char, p.s_embed, p.s_time
        FROM char_candidates c
        LEFT JOIN pair_channel_scores p
          ON p.a_alias_id = c.a_alias_id AND p.b_alias_id = c.b_alias_id
        """
    )
    labels = {
        (r["a_alias_id"], r["b_alias_id"]): r["label"]
        for r in conn.execute(
            "SELECT a_alias_id, b_alias_id, label FROM label_pairs"
        )
    }
    insert = """
        INSERT INTO pair_scores (
          case_id, a_alias_id, b_alias_id,
          s_char, s_embed, s_hard, s_time, n_shared_hard, confidence, label
        ) VALUES (?,?,?,?,?,?,?,?,?,?)
        """
    conn.execute("DELETE FROM pair_scores WHERE case_id = ?", (case_id,))
    xs, meta, n = [], [], 0
    for r in cur:
        sh, ns = pair_hard(ev, r["a_alias_id"], r["b_alias_id"])
        x = impute_row(r["s_char"], r["s_embed"], sh, r["s_time"], ns, means)
        xs.append(x)
        meta.append((r, sh, ns))
        if len(xs) >= 20000:
            n += _flush(conn, insert, case_id, xs, meta, labels, predict_fn)
            xs, meta = [], []
            conn.commit()
    if xs:
        n += _flush(conn, insert, case_id, xs, meta, labels, predict_fn)
    conn.commit()
    return n


def run(
    db_path: str | Path,
    cfg: dict,
    *,
    case_id: str | None = None,
    heuristic: bool = False,
    threshold: float | None = None,
) -> dict:
    init_db(db_path)
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    model_path = MODEL_DIR / ("fusion-heuristic.joblib" if heuristic else "fusion-v1.joblib")
    eval_dir = Path("docs/eval")
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        means = corpus_means(conn)
        ev = evidence_index(conn)
        labeled = _load_labeled_features(conn, means, ev)
        train, test, train_ids, test_ids = alias_disjoint_split(labeled)
        disjoint = train_ids.isdisjoint(test_ids)
        x_train = np.asarray([r["x"] for r in train], dtype=np.float64)
        y_train = np.asarray([r["label"] for r in train], dtype=np.int32)
        x_test = np.asarray([r["x"] for r in test], dtype=np.float64)
        y_test = np.asarray([r["label"] for r in test], dtype=np.int32)
        if heuristic:
            predict = heuristic_confidence
            coefs = {
                "mode": "heuristic_fallback",
                "weights": dict(zip(FEATURE_NAMES[:4], HEURISTIC_WEIGHTS.tolist())),
            }
            version = "heuristic-v1"
        else:
            clf = fit_model(x_train, y_train)
            predict = lambda x: clf.predict_proba(x)[:, 1]
            coefs = dict(zip(FEATURE_NAMES, clf.coef_[0].tolist()))
            coefs["intercept"] = float(clf.intercept_[0])
            version = persist_model(clf, means, model_path)
        proba = predict(x_test)
        thr = float(
            threshold
            if threshold is not None
            else (cfg.get("fusion") or {}).get("confidence_threshold", 0.83)
        )
        held = metrics(y_test, proba, thr)
        if not heuristic:
            save_pr_curve(y_test, proba, eval_dir / "pr_curve.png")
            save_confusion(y_test, proba, thr, eval_dir / "confusion_matrix.png")
        heur_held = metrics(y_test, heuristic_confidence(x_test), thr)

    card = get_case(db_path, case_id) if case_id else None
    if card is None:
        card = create_case(
            db_path, cfg, case_id=case_id, threshold=thr, model_version=version
        )
    set_status(db_path, card["case_id"], "running", model_version=version, threshold=thr)
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        n_scored = score_candidates(conn, card["case_id"], predict, means, ev)
    set_status(db_path, card["case_id"], "complete", model_version=version)

    return {
        "case": get_case(db_path, card["case_id"]),
        "n_labeled": len(labeled),
        "n_train": len(train),
        "n_test": len(test),
        "n_train_pos": int(y_train.sum()),
        "n_test_pos": int(y_test.sum()),
        "alias_disjoint": disjoint,
        "n_train_alias_ids": len(train_ids),
        "n_test_alias_ids": len(test_ids),
        "coefficients": coefs,
        "heldout": held,
        "heuristic_heldout": heur_held,
        "heuristic": heuristic,
        "n_scored": n_scored,
        "pr_curve": str(eval_dir / "pr_curve.png"),
        "confusion_matrix": str(eval_dir / "confusion_matrix.png"),
        "model_path": str(model_path),
    }


def main(argv: list[str] | None = None) -> int:
    import argparse

    import yaml

    parser = argparse.ArgumentParser(description="Fit fusion model and score a case")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--db", default=None)
    parser.add_argument("--case-id", default="CASE-2026-001")
    parser.add_argument("--threshold", type=float, default=None)
    parser.add_argument(
        "--heuristic",
        action="store_true",
        help="Fixed-weight fallback — label every reported confidence as heuristic",
    )
    args = parser.parse_args(argv)
    with open(args.config, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    db_path = args.db or cfg["paths"]["sqlite_db"]
    summary = run(
        db_path,
        cfg,
        case_id=args.case_id,
        heuristic=args.heuristic,
        threshold=args.threshold,
    )
    mode = "HEURISTIC FALLBACK" if summary["heuristic"] else "learned LogisticRegression"
    print(f"fusion ({mode})")
    case = summary["case"]
    print(
        f"  case_id={case['case_id']} status={case['status']} "
        f"threshold={case['threshold']} model_version={case['model_version']}"
    )
    print(f"  config_hash={case['config_hash']}")
    print(f"  corpus_snapshot={case['corpus_snapshot']}")
    print(
        f"  alias_disjoint={summary['alias_disjoint']} "
        f"train_ids={summary['n_train_alias_ids']} test_ids={summary['n_test_alias_ids']}"
    )
    print(
        f"  n_train={summary['n_train']} (pos {summary['n_train_pos']}) "
        f"n_test={summary['n_test']} (pos {summary['n_test_pos']})"
    )
    print(f"  coefficients={json.dumps(summary['coefficients'], indent=2)}")
    print(f"  heldout={summary['heldout']}")
    print(f"  heuristic_heldout (smoke, not headline)={summary['heuristic_heldout']}")
    print(f"  n_scored={summary['n_scored']}")
    print(f"  plots={summary['pr_curve']} {summary['confusion_matrix']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
