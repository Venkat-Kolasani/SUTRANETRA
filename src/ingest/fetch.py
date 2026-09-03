"""Download DNM archive tarballs into data/raw/. Idempotent."""

from __future__ import annotations

from pathlib import Path

import requests

XZ_MAGIC = b"\xfd7zXZ\x00"

CANNABISROAD3_URL = (
    "https://archive.org/download/dnmarchives/cannabisroad3-forums.tar.xz"
)
CANNABISROAD3_NAME = "cannabisroad3-forums.tar.xz"


def archive_path(raw_dir: str | Path, filename: str = CANNABISROAD3_NAME) -> Path:
    return Path(raw_dir) / filename


def is_valid_xz(path: Path) -> bool:
    if not path.is_file() or path.stat().st_size == 0:
        return False
    with path.open("rb") as f:
        return f.read(6) == XZ_MAGIC


def fetch_archive(
    dest_dir: str | Path,
    url: str = CANNABISROAD3_URL,
    filename: str = CANNABISROAD3_NAME,
    timeout: int = 120,
) -> Path:
    dest = archive_path(dest_dir, filename)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if is_valid_xz(dest):
        return dest

    resp = requests.get(url, stream=True, timeout=timeout)
    resp.raise_for_status()
    tmp = dest.with_suffix(dest.suffix + ".part")
    with tmp.open("wb") as f:
        for chunk in resp.iter_content(chunk_size=1024 * 256):
            if chunk:
                f.write(chunk)
    if not is_valid_xz(tmp):
        tmp.unlink(missing_ok=True)
        raise ValueError(
            f"download is not a valid xz file (archive.org may have returned HTML): {url}"
        )
    tmp.replace(dest)
    return dest
