"""Download an external corpus file at a pinned revision and verify its bytes.

Every loader here used to fetch from a Hugging Face `resolve/main` URL. `main` is a mutable
branch: a dataset can be re-uploaded, relabelled or repartitioned upstream, and a later run
would then evaluate different bytes while producing numbers that look directly comparable to
the ones in `docs/results/`. Nothing would fail, and the results would silently stop meaning
what the pre-registrations say they mean.

So each file is pinned twice over: the URL names an immutable **commit revision**, and the
downloaded bytes must match a recorded **SHA-256** before anything reads them. A mismatch is
an error, never a warning -- a corpus that is not the corpus we pre-registered against is not
a corpus we can report on.
"""

from __future__ import annotations

import hashlib
import urllib.request
from pathlib import Path

CHUNK = 1 << 20


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


class CorpusIntegrityError(RuntimeError):
    """Raised when downloaded or cached corpus bytes are not the pinned ones."""


def fetch(url: str, path: Path, expected_sha256: str, *, timeout: int = 300) -> Path:
    """Return a local path holding exactly the pinned bytes, downloading if needed.

    A cached file whose digest does not match is treated as corrupt and re-downloaded once,
    because a half-written file from an interrupted run is the common case and is harmless
    to replace. If the freshly downloaded bytes still do not match, that is upstream drift
    or tampering and the run stops.
    """
    if path.exists():
        if sha256_of(path) == expected_sha256:
            return path
        path.unlink()

    path.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url, timeout=timeout) as response:  # noqa: S310 - pinned host
        path.write_bytes(response.read())

    actual = sha256_of(path)
    if actual != expected_sha256:
        path.unlink(missing_ok=True)
        raise CorpusIntegrityError(
            f"{url} does not match its pinned digest.\n"
            f"  expected sha256 {expected_sha256}\n"
            f"  actual   sha256 {actual}\n"
            "The pinned revision should be immutable, so this means the recorded digest is "
            "wrong or the source changed. Do not update the digest to make this pass without "
            "re-reading the corpus and confirming the pre-registered mapping still holds."
        )
    return path
