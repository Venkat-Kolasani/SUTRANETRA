"""Checksum-validate BTC candidates; reject the spec's known false positives."""

from src.evidence.crypto_addr import extract_crypto, is_valid_btc

# Real addresses from cannabisroad3 post bodies (SPEC.md §7.2 / §18).
REAL_BTC = (
    "1LqD2vdKM8iSP2G6qWQd5iQ9GNKhBPTgB6",
    "1CatnMd3jsEKhwhSLUf8V862im8gBp3NDF",
    "1JoLLy5gwsMQUMavyqZeXwUoHBb693ZeYm",
    "1DSD3B3uS2wGZjZAwa2dqQ7M9v7Ajw2iLy",
)
MD5_FP = "16936e5adb8a36cbb21d38beeb6f8e11"
SHORT_FP = "3y4kBQhzP5dPh1AiMhNWU7HKLB3"


def test_real_corpus_addresses_pass_base58check():
    for addr in REAL_BTC:
        assert is_valid_btc(addr), addr


def test_known_false_positives_rejected():
    assert not is_valid_btc(MD5_FP)
    assert not is_valid_btc(SHORT_FP)


def test_extractor_keeps_real_and_drops_false_positives():
    blob = " ".join(REAL_BTC + (MD5_FP, SHORT_FP))
    hits = {h["value"] for h in extract_crypto(blob) if h["kind"] == "btc"}
    assert set(REAL_BTC) <= hits
    assert MD5_FP not in hits
    assert SHORT_FP not in hits
