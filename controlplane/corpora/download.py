"""Pinned, checksum-verified downloads for optional public-corpus evaluations."""

from __future__ import annotations

import hashlib
import urllib.request
from pathlib import Path


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ensure_cached_file(
    *, url: str, path: Path, sha256: str, timeout_seconds: int
) -> Path:
    """Return a verified cache entry, downloading atomically when it is absent.

    Existing mismatches are never silently replaced: a changed cache is evidence worth
    investigating. New downloads are written beside the destination and promoted only
    after their SHA-256 matches the pre-registered file.
    """
    if path.exists():
        actual = file_sha256(path)
        if actual != sha256:
            raise ValueError(
                f"Checksum mismatch for cached corpus file {path}: expected {sha256}, "
                f"found {actual}. Remove the cache entry and retry only after checking provenance."
            )
        return path

    path.parent.mkdir(parents=True, exist_ok=True)
    staging = path.with_name(f"{path.name}.partial")
    try:
        with (
            urllib.request.urlopen(url, timeout=timeout_seconds) as response,  # noqa: S310
            staging.open("wb") as handle,
        ):
            while chunk := response.read(1024 * 1024):
                handle.write(chunk)
        actual = file_sha256(staging)
        if actual != sha256:
            raise ValueError(
                f"Checksum mismatch for downloaded corpus file {path.name}: "
                f"expected {sha256}, found {actual}."
            )
        staging.replace(path)
    except BaseException:
        staging.unlink(missing_ok=True)
        raise
    return path
