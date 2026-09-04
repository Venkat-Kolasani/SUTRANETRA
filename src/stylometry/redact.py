"""Alias redaction for the blind-evaluation protocol (SPEC.md §8.4).

Dropping the username from the pair *label* is not enough: handles show up in
signatures (`- AngelEyes`) and PGP UIDs (`AngelEyes <...>`). If those strings
reach a char n-gram vectorizer, S_char is string-matching, not style.
"""

from __future__ import annotations

import re

_LEET = {
    "a": r"[a4@]",
    "e": r"[e3]",
    "i": r"[i1!]",
    "l": r"[l1]",
    "o": r"[o0]",
    "s": r"[s5$]",
    "t": r"[t7]",
}
_SEP = r"[\s_\-]*"
_TRAIL_DIGITS = re.compile(r"\d+$")


def _stems(alias: str) -> list[str]:
    alias = (alias or "").strip()
    if not alias:
        return []
    out = [alias]
    stem = _TRAIL_DIGITS.sub("", alias).rstrip("_- ")
    if stem and stem != alias and len(stem) >= 3:
        out.append(stem)
    return out


def _pattern_for(alias: str) -> re.Pattern[str] | None:
    parts: list[str] = []
    for ch in alias:
        if ch in " \t_-":
            continue
        key = ch.lower()
        if key in _LEET:
            parts.append(_LEET[key])
        elif ch.isalnum():
            parts.append(re.escape(ch))
        else:
            parts.append(re.escape(ch))
    if len(parts) < 2:
        return None
    body = _SEP.join(parts)
    return re.compile(rf"(?<![A-Za-z0-9]){body}\d*(?![A-Za-z0-9])", re.I)


def redact_aliases(text: str, *aliases: str) -> str:
    """Remove each alias and near-variants (separators, digits, leetspeak)."""
    out = text or ""
    seen: set[str] = set()
    for alias in aliases:
        for stem in _stems(alias):
            key = stem.lower()
            if key in seen:
                continue
            seen.add(key)
            pat = _pattern_for(stem)
            if pat is None:
                continue
            out = pat.sub(" ", out)
    return out
