"""PGP armor / bare fingerprints → stored fingerprint or key id (SPEC.md §7.1)."""

from __future__ import annotations

import re
import sys
import types

# ponytail: pgpy 0.6 imports stdlib imghdr, removed in Python 3.13. Stub until
# pgpy drops it; do not install a backport just for that import.
if "imghdr" not in sys.modules:
    _imghdr = types.ModuleType("imghdr")
    _imghdr.what = lambda *a, **k: None  # type: ignore[method-assign]
    sys.modules["imghdr"] = _imghdr

from pgpy import PGPKey, PGPMessage  # noqa: E402
import warnings

warnings.filterwarnings("ignore", message="Incorrect crc24")
warnings.filterwarnings("ignore", message="Discarded unexpected packet")
warnings.filterwarnings("ignore", message="Warning: Orphaned packet")

from src.evidence.htmltext import html_to_text

PUBKEY_RE = re.compile(
    r"-----BEGIN PGP PUBLIC KEY BLOCK-----.*?-----END PGP PUBLIC KEY BLOCK-----",
    re.S,
)
SIGNED_RE = re.compile(
    r"-----BEGIN PGP SIGNED MESSAGE-----.*?-----END PGP SIGNATURE-----",
    re.S,
)
BARE_FPR_RE = re.compile(r"\b[0-9A-Fa-f]{40}\b")
GROUPED_FPR_RE = re.compile(r"(?:[0-9A-Fa-f]{4}\s+){9}[0-9A-Fa-f]{4}")
KEYID_RE = re.compile(
    r"(?:Key[- ]?ID|keyid)[:\s]*([0-9A-Fa-f]{8,16})",
    re.I,
)
HEX16_RE = re.compile(r"\b[0-9A-Fa-f]{16}\b")


def _norm_fpr(value: str) -> str:
    return re.sub(r"\s+", "", value).upper()


def _context(text: str, start: int, end: int) -> str:
    lo = max(0, start - 120)
    hi = min(len(text), end + 120)
    return text[lo:hi]


def _fingerprint_from_key_blob(blob: str) -> str | None:
    try:
        key, _rest = PGPKey.from_blob(blob)
        return _norm_fpr(str(key.fingerprint))
    except Exception:
        return None


def _fallback_key_id(blob: str) -> str | None:
    m = KEYID_RE.search(blob)
    if m:
        return m.group(1).upper()
    m = HEX16_RE.search(blob)
    return m.group(0).upper() if m else None


def _signer_from_signed(blob: str) -> str | None:
    try:
        msg = PGPMessage.from_blob(blob)
        for sig in getattr(msg, "signatures", []) or []:
            fpr = getattr(sig, "signer", None) or getattr(sig, "hash2", None)
            if fpr:
                return _norm_fpr(str(fpr))
        signer = getattr(msg, "signer", None)
        if signer:
            return _norm_fpr(str(signer))
    except Exception:
        pass
    return _fallback_key_id(blob)


def extract_pgp(text: str) -> list[dict]:
    out: list[dict] = []
    covered: list[tuple[int, int]] = []
    seen: set[str] = set()

    def add(value: str, start: int, end: int, note: str = "") -> None:
        value = _norm_fpr(value)
        if not value or value == "NONE":
            return
        if not re.fullmatch(r"[0-9A-F]{8}|[0-9A-F]{16}|[0-9A-F]{40}", value):
            return
        if value in seen:
            return
        seen.add(value)
        row = {
            "kind": "pgp_fpr",
            "value": value,
            "context": _context(text, start, end),
        }
        if note:
            row["context"] = note + " | " + row["context"]
        out.append(row)

    for m in PUBKEY_RE.finditer(text):
        blob = "\n".join(ln.rstrip() for ln in m.group(0).splitlines())
        covered.append((m.start(), m.end()))
        fpr = _fingerprint_from_key_blob(blob)
        if fpr:
            add(fpr, m.start(), m.end())
        else:
            kid = _fallback_key_id(blob)
            if kid:
                add(kid, m.start(), m.end(), note="pgpy-parse-failed")

    for m in SIGNED_RE.finditer(text):
        blob = "\n".join(ln.rstrip() for ln in m.group(0).splitlines())
        covered.append((m.start(), m.end()))
        kid = _signer_from_signed(blob)
        if kid:
            add(kid, m.start(), m.end())

    def inside(pos: int) -> bool:
        return any(a <= pos < b for a, b in covered)

    for m in GROUPED_FPR_RE.finditer(text):
        if inside(m.start()):
            continue
        add(_norm_fpr(m.group(0)), m.start(), m.end())
    for m in BARE_FPR_RE.finditer(text):
        if inside(m.start()):
            continue
        add(m.group(0), m.start(), m.end())
    return out


def extract_pgp_from_html(raw_html: str, body: str = "") -> list[dict]:
    text = html_to_text(raw_html)
    if body:
        text = text + "\n" + body
    return extract_pgp(text)
