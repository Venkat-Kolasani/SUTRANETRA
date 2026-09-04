"""Strip quote/signature/PGP/URL/boilerplate before any stylometry vectorizer.

Quoted text is the classic false-positive leak: if A quotes B, both alias
documents contain B's words. Remove it; do not down-weight it.
"""

from __future__ import annotations

import re

from lxml import html as lhtml

_PGP = re.compile(
    r"-----BEGIN PGP .+?-----.*?-----END PGP .+?-----",
    re.S | re.I,
)
_URL = re.compile(
    r"https?://\S+|www\.\S+|\b[a-z0-9.-]+\.onion(?:/\S*)?",
    re.I,
)
_BOILER_LINE = re.compile(
    r"^(?:quote from:.*|logged|report to moderator|last edit:.*|"
    r"pages:\s*\d.*|re:\s+.*)$",
    re.I | re.M,
)
_SLOW = re.compile(
    r"bbc_standard_quote|<blockquote\b|quoteheader|class=\"quote\"",
    re.I,
)
_WS = re.compile(r"[ \t]+")
_NL = re.compile(r"\n{3,}")

# Inner post body — not the poster sidebar / quote-button chrome.
_INNER_XPATH = (
    './/div[contains(concat(" ", normalize-space(@class), " "), " inner ")]'
    ' | .//div[contains(concat(" ", normalize-space(@class), " "), " postmsg ")]'
)
_QUOTE_XPATH = (
    ".//blockquote"
    ' | .//div[contains(@class, "quote")]'
    ' | .//cite[contains(@class, "quote")]'
)
_SIG_XPATH = (
    './/div[contains(@class, "signature")]'
    ' | .//div[contains(@class, "postsignature")]'
    ' | .//div[contains(@class, "sig")]'
)


def _drop(nodes) -> None:
    for el in nodes:
        parent = el.getparent()
        if parent is not None:
            parent.remove(el)


def hygienize(raw_html: str, body: str = "") -> str:
    """Return the poster's own writing, suitable for vectorization."""
    blob = raw_html or body or ""
    if not blob.strip():
        return ""
    if raw_html and _SLOW.search(raw_html):
        try:
            tree = lhtml.fromstring(raw_html)
        except Exception:
            text = body or blob
        else:
            inners = tree.xpath(_INNER_XPATH)
            root = inners[0] if inners else tree
            _drop(root.xpath(_QUOTE_XPATH))
            _drop(tree.xpath(_SIG_XPATH))
            text = root.text_content()
    else:
        text = body or blob
    text = _PGP.sub(" ", text)
    text = _URL.sub(" ", text)
    text = _BOILER_LINE.sub("", text)
    text = _WS.sub(" ", text)
    text = _NL.sub("\n\n", text)
    return text.strip()
