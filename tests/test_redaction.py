"""Blind-protocol alias redaction (SPEC.md §8.4 / Prompt 05)."""

from src.stylometry.redact import redact_aliases


def test_signature_and_pgp_uid_lose_the_handle():
    signed = "shipped this morning\n- AngelEyes"
    uid = "AngelEyes <angeleyes@lelantos.org>"
    out_sig = redact_aliases(signed, "AngelEyes")
    out_uid = redact_aliases(uid, "AngelEyes")
    assert "AngelEyes" not in out_sig
    assert "angeleyes" not in out_sig.lower()
    assert "AngelEyes" not in out_uid
    assert "angeleyes" not in out_uid.lower()


def test_separator_and_leetspeak_variants():
    text = "contact Angel_Eyes or 4ngelEyes on jabber"
    out = redact_aliases(text, "AngelEyes")
    assert "Angel_Eyes" not in out
    assert "4ngelEyes" not in out
    assert "angeleyes" not in out.lower()
