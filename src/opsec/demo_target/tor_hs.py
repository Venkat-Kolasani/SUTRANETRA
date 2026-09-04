"""Start a local Tor hidden service mapped to the demo HTTP port. Our HS only."""

from __future__ import annotations

import shutil
import subprocess
import time
from pathlib import Path


def write_torrc(hs_dir: Path, data_dir: Path, http_port: int, socks_port: int) -> Path:
    hs_dir = hs_dir.resolve()
    data_dir = data_dir.resolve()
    state = data_dir / "state"
    hs_dir.mkdir(parents=True, exist_ok=True)
    state.mkdir(parents=True, exist_ok=True)
    hs_dir.chmod(0o700)
    state.chmod(0o700)
    torrc = data_dir / "torrc"
    torrc.write_text(
        "\n".join(
            [
                f"DataDirectory {state}",
                f"SocksPort 127.0.0.1:{socks_port}",
                "ControlPort 0",
                f"HiddenServiceDir {hs_dir}",
                f"HiddenServicePort 80 127.0.0.1:{http_port}",
                "Log notice stdout",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return torrc


def start_tor(torrc: Path, hostname_path: Path, timeout: float = 90.0) -> subprocess.Popen:
    tor = shutil.which("tor") or "/opt/homebrew/opt/tor/bin/tor"
    log_path = torrc.parent / "tor.log"
    proc = subprocess.Popen(
        [tor, "-f", str(torrc)],
        stdout=open(log_path, "w"),
        stderr=subprocess.STDOUT,
        text=True,
    )
    deadline = time.time() + timeout
    while time.time() < deadline:
        if hostname_path.exists() and hostname_path.read_text().strip():
            return proc
        if proc.poll() is not None:
            extra = log_path.read_text(encoding="utf-8") if log_path.exists() else ""
            raise RuntimeError(f"tor exited {proc.returncode}: {extra}")
        time.sleep(0.5)
    proc.terminate()
    raise TimeoutError("tor did not write HiddenService hostname in time")


def onion_from(hs_dir: Path) -> str:
    return (hs_dir / "hostname").read_text(encoding="utf-8").strip()
