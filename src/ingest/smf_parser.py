"""SMF 2.0 topic-page parser (SPEC.md §6). Stream HTML in; never extract archives."""

from __future__ import annotations

import hashlib
import html as html_lib
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from bs4 import BeautifulSoup

TS_FMT = "%B %d, %Y, %I:%M:%S %p"
USER_ID_RE = re.compile(r"action=profile;u=(\d+)")
MSG_ID_RE = re.compile(r"^msg_(\d+)$")
ONION_RE = re.compile(
    r"https?://([a-z2-7]{16}|[a-z2-7]{56})\.onion", re.IGNORECASE
)
POSTCOUNT_RE = re.compile(r"(\d+)")
KARMA_RE = re.compile(r"([+-]?\d+)\s*/\s*([+-]?\d+)")
TODAY_RE = re.compile(r"Today at\s+(\d{1,2}:\d{2}:\d{2}\s*[AP]M)", re.IGNORECASE)
YESTERDAY_RE = re.compile(
    r"Yesterday at\s+(\d{1,2}:\d{2}:\d{2}\s*[AP]M)", re.IGNORECASE
)
ON_TS_RE = re.compile(r"on:\s*(.+)", re.IGNORECASE)
THREAD_ID_RE = re.compile(r"topic=(\d+)")
TIME_FMT = "%I:%M:%S %p"


@dataclass
class Post:
    market: str
    msg_id: int
    alias: str
    user_id: int | None
    thread_id: int
    subject: str
    ts: datetime | None
    body: str
    raw_html: str
    onion_host: str | None
    source_archive: str
    scrape_date: date
    source_member_path: str
    content_sha256: str
    membergroup: str | None = None
    postcount: int | None = None
    karma_pos: int | None = None
    karma_neg: int | None = None


def content_sha256(raw_html: str) -> str:
    return hashlib.sha256(raw_html.encode("utf-8")).hexdigest()


def parse_timestamp(text: str, scrape_date: date) -> datetime | None:
    cleaned = html_lib.unescape(text)
    cleaned = cleaned.replace("«", " ").replace("»", " ")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    m = TODAY_RE.search(cleaned)
    if m:
        try:
            t = datetime.strptime(m.group(1).strip(), TIME_FMT).time()
            return datetime.combine(scrape_date, t)
        except ValueError:
            return None
    m = YESTERDAY_RE.search(cleaned)
    if m:
        try:
            t = datetime.strptime(m.group(1).strip(), TIME_FMT).time()
            return datetime.combine(scrape_date - timedelta(days=1), t)
        except ValueError:
            return None
    m = ON_TS_RE.search(cleaned)
    candidate = m.group(1).strip() if m else cleaned
    candidate = candidate.strip(" :")
    try:
        return datetime.strptime(candidate, TS_FMT)
    except ValueError:
        return None


def _int_or_none(text: str | None, pattern: re.Pattern[str]) -> int | None:
    if not text:
        return None
    m = pattern.search(text)
    return int(m.group(1)) if m else None


def _msg_id(wrapper) -> int | None:
    for el in (wrapper, wrapper.find("div", class_="inner")):
        if el is None:
            continue
        m = MSG_ID_RE.match(el.get("id") or "")
        if m:
            return int(m.group(1))
    for el in wrapper.find_all(id=True):
        m = MSG_ID_RE.match(el.get("id") or "")
        if m:
            return int(m.group(1))
    return None


def _body_text(inner) -> str:
    clone = BeautifulSoup(str(inner), "lxml")
    root = clone.find("div", class_="inner") or clone
    for br in root.find_all("br"):
        br.replace_with("\n")
    return html_lib.unescape(root.get_text())


def parse_topic_page(
    html: str,
    market: str,
    *,
    source_archive: str,
    scrape_date: date,
    source_member_path: str,
    thread_id: int | None = None,
) -> list[Post]:
    soup = BeautifulSoup(html, "lxml")
    if thread_id is None:
        m = THREAD_ID_RE.search(source_member_path)
        thread_id = int(m.group(1)) if m else 0

    posts: list[Post] = []
    for wrapper in soup.select("div.post_wrapper"):
        msg_id = _msg_id(wrapper)
        if msg_id is None:
            continue
        alias_el = wrapper.select_one("div.poster h4 a")
        alias = alias_el.get_text(strip=True) if alias_el else ""
        if not alias:
            continue
        href = alias_el.get("href") if alias_el else None
        um = USER_ID_RE.search(href or "")
        user_id = int(um.group(1)) if um else None

        mg_el = wrapper.select_one("li.membergroup")
        membergroup = mg_el.get_text(strip=True) if mg_el else None
        pc_el = wrapper.select_one("li.postcount")
        postcount = _int_or_none(pc_el.get_text() if pc_el else None, POSTCOUNT_RE)
        karma_el = wrapper.select_one("li.karma")
        karma_pos = karma_neg = None
        if karma_el:
            km = KARMA_RE.search(karma_el.get_text())
            if km:
                karma_pos = abs(int(km.group(1)))
                karma_neg = abs(int(km.group(2)))

        subj_el = wrapper.select_one("div.keyinfo h5 a")
        subject = subj_el.get_text(strip=True) if subj_el else ""
        ts_el = wrapper.select_one("div.keyinfo div.smalltext")
        ts = parse_timestamp(ts_el.get_text() if ts_el else "", scrape_date)

        inner = wrapper.select_one("div.post div.inner")
        body = _body_text(inner) if inner else ""
        raw_html = str(wrapper)
        onion_m = ONION_RE.search(raw_html)
        onion_host = f"{onion_m.group(1).lower()}.onion" if onion_m else None

        posts.append(
            Post(
                market=market,
                msg_id=msg_id,
                alias=alias,
                user_id=user_id,
                thread_id=thread_id,
                subject=subject,
                ts=ts,
                body=body,
                raw_html=raw_html,
                onion_host=onion_host,
                source_archive=source_archive,
                scrape_date=scrape_date,
                source_member_path=source_member_path,
                content_sha256=content_sha256(raw_html),
                membergroup=membergroup,
                postcount=postcount,
                karma_pos=karma_pos,
                karma_neg=karma_neg,
            )
        )
    return posts
