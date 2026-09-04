"""Fallback parser for phpBB/PunBB-like topic pages."""

from __future__ import annotations

import re
from datetime import date, datetime

from bs4 import BeautifulSoup

from src.ingest.smf_parser import ONION_RE, Post, content_sha256

USER_ID_RE = re.compile(r"profile\.php\?id=(\d+)")
MSG_ID_RE = re.compile(r"^p(\d+)$")
THREAD_ID_RE = re.compile(r"viewtopic\.php\?id=(\d+)")
POSTCOUNT_RE = re.compile(r"Posts:\s*(\d+)", re.IGNORECASE)


def _int_or_none(text: str | None, pattern: re.Pattern[str]) -> int | None:
    if not text:
        return None
    match = pattern.search(text)
    return int(match.group(1)) if match else None


def _body_text(postmsg) -> str:
    clone = BeautifulSoup(str(postmsg), "lxml")
    root = clone.find("div", class_="postmsg") or clone
    for br in root.find_all("br"):
        br.replace_with("\n")
    return root.get_text("\n").strip()


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
        match = THREAD_ID_RE.search(source_member_path)
        thread_id = int(match.group(1)) if match else 0

    posts: list[Post] = []
    for wrapper in soup.select("div.blockpost"):
        msg_match = MSG_ID_RE.match(wrapper.get("id") or "")
        if not msg_match:
            continue
        msg_id = int(msg_match.group(1))

        alias_el = wrapper.select_one("div.postleft dt strong a")
        alias = alias_el.get_text(strip=True) if alias_el else ""
        if not alias:
            continue

        href = alias_el.get("href") if alias_el else None
        user_id = _int_or_none(href, USER_ID_RE)

        membergroup_el = wrapper.select_one("dd.usertitle strong") or wrapper.select_one(
            "dd.usertitle"
        )
        membergroup = membergroup_el.get_text(strip=True) if membergroup_el else None

        postcount = None
        for dd in wrapper.select("div.postleft dd"):
            text = dd.get_text(" ", strip=True)
            postcount = _int_or_none(text, POSTCOUNT_RE) or postcount

        subject_el = wrapper.select_one("div.postright h3")
        subject = subject_el.get_text(strip=True) if subject_el else ""

        ts = None
        ts_el = wrapper.select_one("h2 a")
        if ts_el:
            try:
                ts = datetime.strptime(ts_el.get_text(strip=True), "%Y-%m-%d %H:%M:%S")
            except ValueError:
                ts = None

        body_el = wrapper.select_one("div.postright div.postmsg")
        body = _body_text(body_el) if body_el else ""
        raw_html = str(wrapper)

        onion_match = ONION_RE.search(raw_html)
        onion_host = f"{onion_match.group(1).lower()}.onion" if onion_match else None

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
                karma_pos=None,
                karma_neg=None,
            )
        )
    return posts
