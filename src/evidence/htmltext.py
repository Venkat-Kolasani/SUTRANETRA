"""Unescape forum HTML so PGP armor and addresses are searchable."""

from __future__ import annotations

import html
import re

_BR = re.compile(r"<br\s*/?>", re.I)
_TAG = re.compile(r"<[^>]+>")


def html_to_text(raw: str) -> str:
    text = html.unescape(raw or "")
    text = _BR.sub("\n", text)
    text = _TAG.sub(" ", text)
    return text.replace("\xa0", " ")
