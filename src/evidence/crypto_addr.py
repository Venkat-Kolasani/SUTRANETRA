"""Crypto address candidates → checksum validation (SPEC.md §7.2)."""

from __future__ import annotations

import hashlib
import re
import base58

from src.evidence.htmltext import html_to_text

# Candidate shapes only — never stored without checksum validation.
BTC_LEGACY_RE = re.compile(r"\b[13][a-km-zA-HJ-NP-Z1-9]{25,34}\b")
BECH32_RE = re.compile(r"\b((?:bc|tb)1[ac-hj-np-z02-9]{8,87})\b", re.I)
XMR_RE = re.compile(r"\b[48][0-9AB][1-9A-HJ-NP-Za-km-z]{93}\b")

_BECH32_CHARSET = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"
_BECH32_GEN = (0x3B6A57B2, 0x26508E6D, 0x1EA119FA, 0x3D4233DD, 0x2A1462B3)


def is_valid_btc(addr: str) -> bool:
    """Base58Check: last 4 bytes must equal sha256(sha256(payload))[:4]."""
    try:
        raw = base58.b58decode(addr)
    except ValueError:
        return False
    if len(raw) < 5:
        return False
    payload, checksum = raw[:-4], raw[-4:]
    digest = hashlib.sha256(hashlib.sha256(payload).digest()).digest()[:4]
    return checksum == digest


def _bech32_polymod(values: list[int]) -> int:
    chk = 1
    for v in values:
        b = chk >> 25
        chk = ((chk & 0x1FFFFFF) << 5) ^ v
        for i in range(5):
            if (b >> i) & 1:
                chk ^= _BECH32_GEN[i]
    return chk


def _bech32_hrp_expand(hrp: str) -> list[int]:
    return [ord(x) >> 5 for x in hrp] + [0] + [ord(x) & 31 for x in hrp]


def is_valid_bech32(addr: str) -> bool:
    addr = addr.strip()
    if addr.lower() != addr and addr.upper() != addr:
        return False
    addr = addr.lower()
    if addr.count("1") != 1:
        return False
    hrp, data = addr.rsplit("1", 1)
    if hrp not in ("bc", "tb") or len(data) < 6:
        return False
    try:
        values = [_BECH32_CHARSET.index(c) for c in data]
    except ValueError:
        return False
    return _bech32_polymod(_bech32_hrp_expand(hrp) + values) == 1


# ponytail: compact Keccak-256 (Monero checksum). SHA3 in hashlib is the NIST
# variant and will not match; drop this if a keccak extra is added later.
_KECCAK_RC = (
    0x0000000000000001, 0x0000000000008082, 0x800000000000808A,
    0x8000000080008000, 0x000000000000808B, 0x0000000080000001,
    0x8000000080008081, 0x8000000000008009, 0x000000000000008A,
    0x0000000000000088, 0x0000000080008009, 0x000000008000000A,
    0x000000008000808B, 0x800000000000008B, 0x8000000000008089,
    0x8000000000008003, 0x8000000000008002, 0x8000000000000080,
    0x000000000000800A, 0x800000008000000A, 0x8000000080008081,
    0x8000000000008080, 0x0000000080000001, 0x8000000080008008,
)
_KECCAK_ROT = (
    (0, 36, 3, 41, 18),
    (1, 44, 10, 45, 2),
    (62, 6, 43, 15, 61),
    (28, 55, 25, 21, 56),
    (27, 20, 39, 8, 14),
)


def _rotl64(x: int, n: int) -> int:
    return ((x << n) | (x >> (64 - n))) & 0xFFFFFFFFFFFFFFFF


def keccak_256(data: bytes) -> bytes:
    st = [0] * 25
    rate = 136
    pad = data + b"\x01" + b"\x00" * ((rate - len(data) % rate) - 1)
    pad = pad[:-1] + bytes([pad[-1] | 0x80])
    for off in range(0, len(pad), rate):
        block = pad[off : off + rate]
        for i in range(rate // 8):
            st[i] ^= int.from_bytes(block[i * 8 : (i + 1) * 8], "little")
        # keccak-f[1600]
        for rc in _KECCAK_RC:
            c = [st[i] ^ st[i + 5] ^ st[i + 10] ^ st[i + 15] ^ st[i + 20] for i in range(5)]
            d = [c[(i - 1) % 5] ^ _rotl64(c[(i + 1) % 5], 1) for i in range(5)]
            for i in range(25):
                st[i] ^= d[i % 5]
            b = [0] * 25
            for x in range(5):
                for y in range(5):
                    b[y + ((2 * x + 3 * y) % 5) * 5] = _rotl64(st[x + 5 * y], _KECCAK_ROT[x][y])
            for i in range(25):
                st[i] = b[i] ^ ((~b[(i // 5) * 5 + (i + 1) % 5]) & b[(i // 5) * 5 + (i + 2) % 5])
            st[0] ^= rc
    return b"".join(st[i].to_bytes(8, "little") for i in range(4))


def is_valid_xmr(addr: str) -> bool:
    try:
        raw = base58.b58decode(addr)
    except ValueError:
        return False
    if len(raw) < 5:
        return False
    return keccak_256(raw[:-4])[:4] == raw[-4:]


def _hits(kind: str, value: str, text: str, start: int, end: int) -> dict:
    lo = max(0, start - 120)
    hi = min(len(text), end + 120)
    return {"kind": kind, "value": value, "context": text[lo:hi]}


def extract_crypto(text: str) -> list[dict]:
    out: list[dict] = []
    seen: set[tuple[str, str]] = set()

    def add(kind: str, value: str, start: int, end: int) -> None:
        key = (kind, value)
        if key in seen:
            return
        seen.add(key)
        out.append(_hits(kind, value, text, start, end))

    for m in BTC_LEGACY_RE.finditer(text):
        addr = m.group(0)
        if is_valid_btc(addr):
            add("btc", addr, m.start(), m.end())
    for m in BECH32_RE.finditer(text):
        addr = m.group(1)
        if is_valid_bech32(addr):
            add("btc", addr.lower(), m.start(), m.end())
    for m in XMR_RE.finditer(text):
        addr = m.group(0)
        if is_valid_xmr(addr):
            add("xmr", addr, m.start(), m.end())
    return out


def extract_crypto_from_html(raw_html: str, body: str = "") -> list[dict]:
    text = html_to_text(raw_html)
    if body:
        text = text + "\n" + body
    return extract_crypto(text)
