"""Template sentences include stored evidence and omit missing fields."""

from src.explain.reason import template_sentence

FULL = {
    "a": {"alias": "Alias_A", "market": "silkroad1", "n_posts": 214},
    "b": {"alias": "Alias_C", "market": "agora", "n_posts": 88},
    "confidence": 0.91,
    "s_char": 0.74,
    "s_embed": 0.22,
    "s_hard": 0.875,
    "s_time": 0.81,
    "shared_evidence": [
        {"kind": "pgp_fpr", "value": "A1B2C3D4E5F60718293A4B5C6D7E8F9012349F0", "n_posts": 3},
        {"kind": "btc", "value": "1FTYtwxxxxxxxxxxxxxxxxxxxxxx4PSK", "n_posts": 2},
    ],
    "timezone": {"shared_utc_offset": 1},
}


def test_sentence_includes_present_evidence_excludes_missing():
    text = template_sentence(FULL)
    assert "`Alias_A` (silkroad1, 214 posts)" in text
    assert "`Alias_C` (agora, 88 posts)" in text
    assert "confidence 0.91" in text
    assert "Shared PGP fingerprint" in text
    assert "A1B2C3" in text
    assert "in 3 posts" in text
    assert "Shared BTC address" in text
    assert "1FTYtw" in text
    assert "Stylometric similarity 0.74 (char n-gram)" in text
    assert "Posting-hour overlap 0.81" in text
    assert "UTC+1" in text
    assert "None" not in text
    sparse = {
        "a": {"alias": "thin", "market": "nucleus", "n_posts": 4},
        "b": {"alias": "other", "market": "thehub", "n_posts": 9},
        "confidence": 0.12,
        "s_char": 0.31,
        "s_time": None,
        "shared_evidence": [],
        "timezone": None,
    }
    s2 = template_sentence(sparse)
    assert "`thin` (nucleus, 4 posts)" in s2
    assert "confidence 0.12" in s2
    assert "Stylometric similarity 0.31" in s2
    assert "PGP" not in s2
    assert "BTC" not in s2
    assert "Posting-hour" not in s2
    assert "UTC" not in s2
    assert "None" not in s2
    assert "null" not in s2.lower()
    flooded = dict(FULL)
    flooded["shared_evidence"] = FULL["shared_evidence"] + [
        {"kind": "btc", "value": "1aaaaYYYYYYYYYYYYYYYYYYYYYYYYbbbb", "n_posts": 1},
        {"kind": "btc", "value": "1ccccYYYYYYYYYYYYYYYYYYYYYYYYdddd", "n_posts": 1},
    ]
    s3 = template_sentence(flooded)
    assert "Plus 1 additional shared hard-evidence values." in s3
    assert "1ccccY" not in s3

