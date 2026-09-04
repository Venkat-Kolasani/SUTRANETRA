"""Clearnet / onion / email extraction, including the spec's ***clearnet*** post."""

from pathlib import Path

from src.evidence.extract import extract_from_post
from src.evidence.onion import extract_contacts


def test_dangerousminds_clearnet_from_topic_440_fixture():
    html = (Path(__file__).parent / "fixtures" / "topic_440_2014-11-25.html").read_text(
        encoding="utf-8", errors="replace"
    )
    hits = extract_from_post(html)
    values = {(h["kind"], h["value"]) for h in hits}
    assert ("clearnet", "dangerousminds.net") in values


def test_obfuscated_email_and_onion():
    text = (
        "contact me at vendor [at] example [dot] com "
        "mirror abcdefghijklmnop.onion "
        "and v3 abcdefghijklmnopqrstuvwxyz234567abcdefghijklmnopqrstuvwx.onion"
    )
    hits = {(h["kind"], h["value"]) for h in extract_contacts(text)}
    assert ("email", "vendor@example.com") in hits
    assert ("onion", "abcdefghijklmnop.onion") in hits
