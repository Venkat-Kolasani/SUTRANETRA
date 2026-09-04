"""Hard evidence should dominate topic-only similarity in the fitted model."""

import numpy as np

from src.fusion.model import fit_model


def test_pgp_high_topic_low():
    rng = np.random.RandomState(0)
    n0, n1 = 400, 200
    x0 = rng.rand(n0, 6) * 0.35
    x0[:, 2] = 0.0
    x0[:, 4] = 0.0
    x0[:, 5] = 0.0
    x0[:, 1] = 0.4 + 0.5 * rng.rand(n0)  # some high topic among negatives
    x1 = rng.rand(n1, 6) * 0.25
    x1[:, 2] = 0.875
    x1[:, 4] = np.log1p(1.0)
    x1[:, 5] = 0.0
    x = np.vstack([x0, x1])
    y = np.array([0] * n0 + [1] * n1)
    clf = fit_model(x, y)
    pgp = np.array([[0.12, 0.15, 0.875, 0.4, np.log1p(1.0), 0.0]])
    topic = np.array([[0.18, 0.92, 0.0, 0.4, 0.0, 0.0]])
    pgp_p = float(clf.predict_proba(pgp)[0, 1])
    topic_p = float(clf.predict_proba(topic)[0, 1])
    assert pgp_p > 0.83, pgp_p
    assert topic_p < 0.83, topic_p
