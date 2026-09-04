"""CT pivot extracts sibling domains from a cached Cert Spotter payload (no network)."""

from pathlib import Path

from src.opsec.ct_pivot import cache_path, pivot, save_cache

QUERY = "domain=erowid.org&include_subdomains=true&expand=dns_names&expand=issuer"
QUERY_VAULTS = "domain=vaults.erowid.org&include_subdomains=true&expand=dns_names&expand=issuer"
FIXTURES = Path(__file__).parent / "fixtures"


def test_pivot_siblings_from_cache(tmp_path: Path):
    import json

    raw = json.loads((FIXTURES / "ct_certspotter_erowid.json").read_text())
    save_cache(tmp_path, "certspotter", QUERY, raw)
    vaults = json.loads((FIXTURES / "ct_certspotter_vaults.json").read_text())
    save_cache(tmp_path, "certspotter", QUERY_VAULTS, vaults)
    result = pivot("erowid.org", tmp_path, live=False, recurse=True, max_siblings=8)
    assert result["source"] == "cache"
    assert set(result["siblings"]) >= {"vaults.erowid.org", "cdn.erowid.org"}
    assert "erowid.org" not in result["siblings"]
    assert "images.erowid.org" in result["recurse_siblings"]
    assert result["n_issuances"] == 2
    assert "leafkey111" in result["pubkey_sha256"]
    assert cache_path(tmp_path, "certspotter", QUERY).exists()


def test_cache_miss_does_not_hit_network(tmp_path: Path, monkeypatch):
    def boom(*_a, **_k):
        raise AssertionError("network should not run without --live")

    monkeypatch.setattr("src.opsec.ct_pivot.fetch_certspotter", boom)
    monkeypatch.setattr("src.opsec.ct_pivot.fetch_crtsh", boom)
    result = pivot("no-such-domain.invalid", tmp_path, live=False)
    assert result["source"] == "cache_miss"
    assert result["siblings"] == []
