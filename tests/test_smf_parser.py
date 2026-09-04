"""Golden-file SMF parser test against a real cannabisroad3 thread page."""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

from src.ingest.smf_parser import parse_timestamp, parse_topic_page

FIXTURE = Path(__file__).parent / "fixtures" / "topic_440_2014-11-25.html"
EXPECTED = Path(__file__).parent / "fixtures" / "topic_440_2014-11-25.expected.json"
MEMBER = "cannabisroad3-forums/2014-11-25/index.php?topic=440.0"


def test_parse_topic_440_matches_inspected_html():
    html = FIXTURE.read_text(encoding="utf-8", errors="replace")
    posts = parse_topic_page(
        html,
        "cannabisroad3",
        source_archive="cannabisroad3-forums.tar.xz",
        scrape_date=date(2014, 11, 25),
        source_member_path=MEMBER,
    )
    expected = json.loads(EXPECTED.read_text(encoding="utf-8"))
    assert [(p.msg_id, p.alias, p.ts.isoformat(sep=" ") if p.ts else None, p.body) for p in posts] == [
        (row["msg_id"], row["alias"], row["ts"], row["body"]) for row in expected
    ]
    # Hand-checked against the fixture HTML (SPEC.md §6 sample).
    first = posts[0]
    assert first.alias == "AngelEyes"
    assert first.msg_id == 4111
    assert first.user_id == 389
    assert first.ts == datetime(2014, 7, 10, 3, 26, 3)
    assert first.membergroup == "Cannabis Road Legacy Vendor"
    assert first.postcount == 139
    assert first.karma_pos == 45 and first.karma_neg == 0
    assert first.onion_host == "forumz2gljo2vhzb.onion"
    assert first.body.startswith(
        "This piece on the otherwise unrelated website dangerous minds"
    )


def test_unparseable_timestamp_is_none_not_guessed():
    html = FIXTURE.read_text(encoding="utf-8", errors="replace")
    html = html.replace(
        "July 10, 2014, 03:26:03 AM",
        "not a real timestamp",
        1,
    )
    posts = parse_topic_page(
        html,
        "cannabisroad3",
        source_archive="cannabisroad3-forums.tar.xz",
        scrape_date=date(2014, 11, 25),
        source_member_path=MEMBER,
    )
    assert posts[0].msg_id == 4111
    assert posts[0].ts is None
    assert posts[0].alias == "AngelEyes"


def test_today_at_resolves_against_scrape_date():
    ts = parse_timestamp("Today at 03:26:03 AM", date(2014, 11, 25))
    assert ts == datetime(2014, 11, 25, 3, 26, 3)


SR1_FIXTURE = Path(__file__).parent / "fixtures" / "silkroad1_topic_10_2013-11-03.html"
SR1_MEMBER = "silkroad1-forums/2013-11-03/index.php?topic=10.0"


def test_silkroad1_selectors_and_timestamp_without_seconds():
    html = SR1_FIXTURE.read_text(encoding="utf-8", errors="replace")
    posts = parse_topic_page(
        html,
        "silkroad1",
        source_archive="silkroad1-forums.tar.xz",
        scrape_date=date(2013, 11, 3),
        source_member_path=SR1_MEMBER,
    )
    assert [(p.msg_id, p.alias) for p in posts] == [
        (36, "Egoa"),
        (43, "asdf90"),
        (1861, "khornate"),
        (1892, "rake"),
        (400223, "Zero Gravity"),
        (400319, "SillyStoner"),
    ]
    first = posts[0]
    assert first.ts == datetime(2011, 6, 18, 11, 13)
    assert first.source_archive == "silkroad1-forums.tar.xz"
    assert first.scrape_date == date(2013, 11, 3)
    assert first.source_member_path == SR1_MEMBER
    assert first.body.startswith("I know this has been posted around")
