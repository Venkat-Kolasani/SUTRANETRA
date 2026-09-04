"""Download DNM archive tarballs into data/raw/. Idempotent."""

from __future__ import annotations

from pathlib import Path

import requests
from requests import Response

XZ_MAGIC = b"\xfd7zXZ\x00"

BASE_URL = "https://archive.org/download/dnmarchives"


def archive_filename(market: str) -> str:
    return f"{market}-forums.tar.xz"


def archive_url(market: str) -> str:
    return f"{BASE_URL}/{archive_filename(market)}"


def archive_path(raw_dir: str | Path, market: str = "cannabisroad3") -> Path:
    return Path(raw_dir) / archive_filename(market)


def is_valid_xz(path: Path) -> bool:
    if not path.is_file() or path.stat().st_size == 0:
        return False
    with path.open("rb") as f:
        return f.read(6) == XZ_MAGIC


def _open_response(url: str, tmp: Path, timeout: int) -> tuple[Response, str]:
    offset = tmp.stat().st_size if tmp.exists() else 0
    headers = {"Range": f"bytes={offset}-"} if offset else {}
    resp = requests.get(url, stream=True, timeout=timeout, headers=headers)
    resp.raise_for_status()

    accepts_range = resp.status_code == 206 and offset > 0
    mode = "ab" if accepts_range else "wb"
    if offset and not accepts_range and tmp.exists():
        tmp.unlink()
    return resp, mode


def fetch_archive(
    dest_dir: str | Path,
    market: str = "cannabisroad3",
    timeout: int = 1800,
    max_attempts: int = 5,
) -> Path:
    """Download archive for *market* into *dest_dir*. Skip if already present."""
    dest = archive_path(dest_dir, market)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if is_valid_xz(dest):
        return dest

    url = archive_url(market)
    tmp = dest.with_suffix(dest.suffix + ".part")

    last_error: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            resp, mode = _open_response(url, tmp, timeout)
            with resp, tmp.open(mode) as f:
                for chunk in resp.iter_content(chunk_size=1024 * 256):
                    if chunk:
                        f.write(chunk)
            break
        except requests.RequestException as exc:
            last_error = exc
            if attempt == max_attempts:
                raise

    if not is_valid_xz(tmp):
        tmp.unlink(missing_ok=True)
        if last_error is not None:
            raise ValueError(
                f"download incomplete or invalid after retries: {url}"
            ) from last_error
        raise ValueError(
            f"download is not a valid xz file (archive.org may have returned HTML): {url}"
        )
    tmp.replace(dest)
    return dest
