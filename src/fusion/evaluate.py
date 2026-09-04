"""PR-AUC and operating-point plots (SPEC.md §11.5). Accuracy is not reported."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from sklearn.metrics import (
    PrecisionRecallDisplay,
    average_precision_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
)


def metrics(y_true: np.ndarray, proba: np.ndarray, threshold: float) -> dict:
    pred = (proba >= threshold).astype(int)
    return {
        "threshold": float(threshold),
        "precision": float(precision_score(y_true, pred, zero_division=0)),
        "recall": float(recall_score(y_true, pred, zero_division=0)),
        "f1": float(f1_score(y_true, pred, zero_division=0)),
        "pr_auc": float(average_precision_score(y_true, proba)),
        "n": int(len(y_true)),
        "n_pos": int(y_true.sum()),
        "n_pred_pos": int(pred.sum()),
    }


def save_pr_curve(y_true: np.ndarray, proba: np.ndarray, path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    path.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(6, 5))
    PrecisionRecallDisplay.from_predictions(y_true, proba, ax=ax, name="learned")
    ax.set_title("SUTRANETRA held-out PR curve (alias-disjoint)")
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def save_confusion(y_true: np.ndarray, proba: np.ndarray, threshold: float, path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    path.parent.mkdir(parents=True, exist_ok=True)
    pred = (proba >= threshold).astype(int)
    cm = confusion_matrix(y_true, pred, labels=[0, 1])
    fig, ax = plt.subplots(figsize=(4.5, 4))
    im = ax.imshow(cm, cmap="Blues")
    ax.set_xticks([0, 1], labels=["pred 0", "pred 1"])
    ax.set_yticks([0, 1], labels=["true 0", "true 1"])
    ax.set_title(f"Confusion @ threshold {threshold:.2f}")
    for (i, j), v in np.ndenumerate(cm):
        ax.text(j, i, str(int(v)), ha="center", va="center")
    fig.colorbar(im, ax=ax, fraction=0.046)
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)
