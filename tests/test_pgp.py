"""Armored PGP block from the cannabisroad3 corpus parses to a known fingerprint."""

from pathlib import Path

from src.evidence.pgp import extract_pgp
from src.evidence.score import s_hard, shared_items

FIXTURE = Path(__file__).parent / "fixtures" / "pgp_trappy_msg1596.asc"
# pgpy fingerprint of Trappy's posted public key (cannabisroad3 msg_id=1596).
TRAPPED_FPR = "74D0519647C44BCBC03A182421819BFFDB3D03BC"


def test_corpus_pubkey_parses_to_known_fingerprint():
    armor = FIXTURE.read_text(encoding="utf-8")
    hits = extract_pgp(armor)
    values = [h["value"] for h in hits]
    assert TRAPPED_FPR in values
    assert all(h["kind"] == "pgp_fpr" for h in hits)


def test_html_entity_mangled_armor_still_parses():
    armor = FIXTURE.read_text(encoding="utf-8")
    mangled = armor.replace("-----BEGIN", "-----BEGIN").replace("\n", "<br />")
    from src.evidence.pgp import extract_pgp_from_html

    hits = extract_pgp_from_html(mangled)
    assert TRAPPED_FPR in [h["value"] for h in hits]


def test_pgpy_failure_falls_back_to_key_id_in_armor():
    blob = (
        "-----BEGIN PGP PUBLIC KEY BLOCK-----\n"
        "Comment: Key ID: AABBCCDD11223344\n"
        "not-valid-armor\n"
        "-----END PGP PUBLIC KEY BLOCK-----\n"
    )
    hits = extract_pgp(blob)
    assert hits
    assert hits[0]["value"] == "AABBCCDD11223344"
    assert "pgpy-parse-failed" in hits[0]["context"]


def test_shared_pgp_saturates_near_spec_example():
    shared = shared_items(
        [("pgp_fpr", TRAPPED_FPR)],
        [("pgp_fpr", TRAPPED_FPR)],
    )
    score, n = s_hard(shared)
    assert n == 1
    assert abs(score - 0.875) < 1e-9  # 1 - 0.5**3; spec cites ~0.88


def test_no_shared_evidence_is_exactly_zero():
    score, n = s_hard([])
    assert n == 0
    assert score == 0.0
