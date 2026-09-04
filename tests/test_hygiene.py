"""Quoted text must not reach the vectorizer (SPEC.md §8.4)."""

from datetime import date
from pathlib import Path

from src.ingest.smf_parser import parse_topic_page
from src.stylometry.hygiene import hygienize

FIXTURE = Path("tests/fixtures/topic_440_2014-11-25.html")


def test_quote_block_stripped_from_real_smf_post():
    html = FIXTURE.read_text(encoding="utf-8", errors="replace")
    posts = parse_topic_page(
        html,
        "cannabisroad3",
        source_archive="cannabisroad3-forums.tar.xz",
        scrape_date=date(2014, 11, 25),
        source_member_path="2014-11-25/forumz.../index.php?topic=440.0",
    )
    post = next(p for p in posts if p.msg_id == 4130)
    cleaned = hygienize(post.raw_html, post.body)
    assert "epi pen" not in cleaned.lower()
    assert "whole foods mango bin" not in cleaned.lower()
    assert "sister has the same problem with mangos" in cleaned.lower()
    assert "angeleyes@" not in cleaned.lower()  # signature dropped
