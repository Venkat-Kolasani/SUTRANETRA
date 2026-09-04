"""Golden-file fallback parser test against a real nucleus thread page."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from src.ingest.phpbb_parser import parse_topic_page

FIXTURE = (
    Path(__file__).parent / "fixtures" / "nucleus_viewtopic_10_2014-10-24.html"
)
MEMBER = "nucleus-forums/2014-10-24/viewtopic.php?id=10"


def test_parse_nucleus_viewtopic_matches_inspected_html():
    html = FIXTURE.read_text(encoding="utf-8", errors="replace")
    posts = parse_topic_page(
        html,
        "nucleus",
        source_archive="nucleus-forums.tar.xz",
        scrape_date=date(2014, 10, 24),
        source_member_path=MEMBER,
    )

    assert [(post.msg_id, post.alias) for post in posts] == [(18, "Mellow"), (21, "vrc")]

    first, second = posts

    assert first.user_id == 10
    assert first.thread_id == 10
    assert first.subject == "List Of Working BTC Mixers"
    assert first.ts == datetime(2014, 10, 15, 12, 5, 58)
    assert first.membergroup == "Member"
    assert first.postcount == 1
    assert first.onion_host == "bitmixegkuerln7q.onion"
    assert first.source_archive == "nucleus-forums.tar.xz"
    assert first.scrape_date == date(2014, 10, 24)
    assert first.source_member_path == MEMBER
    assert first.content_sha256
    assert first.raw_html
    assert first.body.startswith(
        "Hi there, most of people who use darknet should to use mixing services"
    )

    assert second.user_id == 3
    assert second.subject == "Re: List Of Working BTC Mixers"
    assert second.ts == datetime(2014, 10, 18, 15, 21, 56)
    assert second.membergroup == "Administrator"
    assert second.postcount == 14
    assert second.onion_host == "z34uj4opd3tejafn.onion"
    assert second.source_archive == "nucleus-forums.tar.xz"
    assert second.scrape_date == date(2014, 10, 24)
    assert second.source_member_path == MEMBER
    assert second.content_sha256
    assert second.body == "Thanks"
