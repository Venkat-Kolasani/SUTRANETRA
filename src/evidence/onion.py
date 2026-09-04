"""Onion hosts, clearnet domains, emails (SPEC.md §7.3)."""

from __future__ import annotations

import re
from urllib.parse import urlparse

from src.evidence.htmltext import html_to_text

ONION_RE = re.compile(
    r"\b([a-z2-7]{56}|[a-z2-7]{16})\.onion\b",
    re.I,
)
URL_RE = re.compile(r"https?://[^\s<>\"']+", re.I)
# Bare domain; TLD is letters so we don't treat 1.2.3.4 as a domain here.
BARE_DOMAIN_RE = re.compile(
    r"\b(?:www\.)?([a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)*\.[a-z]{2,})\b",
    re.I,
)
EMAIL_RE = re.compile(r"\b[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}\b", re.I)
OBFUSCATED_EMAIL_RE = re.compile(
    r"\b([A-Z0-9._%+\-]+)\s*(?:\[at\]|\(at\))\s*([A-Z0-9.\-]+)\s*(?:\[dot\]|\(dot\))\s*([A-Z]{2,})\b",
    re.I,
)

_FILE_TLDS = frozenset(
    "png jpg jpeg gif webp svg css js html htm php asp aspx pdf zip tar gz txt exe".split()
)
_SKIP_DOMAINS = frozenset({"localhost", "example.com", "example.org", "example.net"})
_SKIP_TLDS = frozenset("this that with from have will them they your here".split())


def _ctx(text: str, start: int, end: int) -> str:
    return text[max(0, start - 120) : min(len(text), end + 120)]


def _add(out: list[dict], seen: set[tuple[str, str]], kind: str, value: str, text: str, s: int, e: int) -> None:
    key = (kind, value)
    if key in seen:
        return
    seen.add(key)
    out.append({"kind": kind, "value": value, "context": _ctx(text, s, e)})


def _clean_domain(host: str) -> str | None:
    host = host.strip(".").lower()
    if host.startswith("www."):
        host = host[4:]
    if not host or host.endswith(".onion") or host in _SKIP_DOMAINS:
        return None
    tld = host.rsplit(".", 1)[-1]
    if tld in _FILE_TLDS or tld in _SKIP_TLDS:
        return None
    if host.count(".") < 1:
        return None
    return host


def extract_contacts(text: str) -> list[dict]:
    out: list[dict] = []
    seen: set[tuple[str, str]] = set()

    for m in ONION_RE.finditer(text):
        host = m.group(0).lower()
        _add(out, seen, "onion", host, text, m.start(), m.end())

    for m in EMAIL_RE.finditer(text):
        _add(out, seen, "email", m.group(0).lower(), text, m.start(), m.end())
    for m in OBFUSCATED_EMAIL_RE.finditer(text):
        email = f"{m.group(1)}@{m.group(2)}.{m.group(3)}".lower()
        email = email.replace("..", ".")
        _add(out, seen, "email", email, text, m.start(), m.end())

    for m in URL_RE.finditer(text):
        try:
            parsed = urlparse(m.group(0))
        except ValueError:
            continue
        host = _clean_domain(parsed.hostname or "")
        if host:
            _add(out, seen, "clearnet", host, text, m.start(), m.end())

    for m in BARE_DOMAIN_RE.finditer(text):
        host = _clean_domain(m.group(1))
        if host:
            _add(out, seen, "clearnet", host, text, m.start(), m.end())

    return out


def extract_contacts_from_html(raw_html: str, body: str = "") -> list[dict]:
    text = html_to_text(raw_html)
    if body:
        text = text + "\n" + body
    return extract_contacts(text)
