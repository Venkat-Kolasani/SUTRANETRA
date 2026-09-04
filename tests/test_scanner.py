"""Every planted demo-target misconfiguration is detected by name."""

from src.opsec.demo_target.app import CLEARNET_DOMAIN, GIT_REMOTE, SERVER_AT_HOST
from src.opsec.demo_target.serve import serve_in_thread
from src.opsec.scanner import scan_target

PLANTED = {
    "clearnet_ref",
    "server_status",
    "git_config",
    "env_leak",
    "backup_leak",
    "config_bak",
    "dir_listing",
    "server_header",
    "x_powered_by",
    "default_page",
    "tls_san",
}


def test_scanner_detects_every_planted_misconfig():
    info = serve_in_thread()
    try:
        findings = scan_target(info["http"], info["https"])
    finally:
        info["stop"]()
    kinds = {f["finding_kind"] for f in findings}
    missing = PLANTED - kinds
    assert not missing, missing
    by = {f["finding_kind"]: f for f in findings}
    assert CLEARNET_DOMAIN in by["clearnet_ref"]["value"]
    assert by["server_status"]["value"] == SERVER_AT_HOST
    assert GIT_REMOTE in by["git_config"]["value"]
    assert by["env_leak"]["value"] == "/.env"
    assert by["backup_leak"]["value"] == "/backup.zip"
    assert by["config_bak"]["value"] == "/config.php.bak"
    assert by["dir_listing"]["value"] == "/files/"
    assert "Apache" in by["server_header"]["value"]
    assert "PHP" in by["x_powered_by"]["value"]
    assert "nginx" in by["default_page"]["detail"].lower()
    assert CLEARNET_DOMAIN in by["tls_san"]["value"]
