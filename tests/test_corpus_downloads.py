from __future__ import annotations

import hashlib
import io
from pathlib import Path

import pytest

from controlplane.corpora.download import ensure_cached_file


def test_download_is_verified_before_atomic_promotion(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    payload = b"pinned public corpus bytes"
    expected = hashlib.sha256(payload).hexdigest()
    monkeypatch.setattr("urllib.request.urlopen", lambda *_args, **_kwargs: io.BytesIO(payload))

    target = tmp_path / "nested" / "corpus.bin"
    assert ensure_cached_file(
        url="https://example.invalid/corpus.bin",
        path=target,
        sha256=expected,
        timeout_seconds=1,
    ) == target
    assert target.read_bytes() == payload
    assert not target.with_name("corpus.bin.partial").exists()


def test_existing_checksum_mismatch_is_not_silently_replaced(tmp_path: Path) -> None:
    target = tmp_path / "corpus.bin"
    target.write_bytes(b"changed")

    with pytest.raises(ValueError, match="Checksum mismatch for cached corpus file"):
        ensure_cached_file(
            url="https://example.invalid/corpus.bin",
            path=target,
            sha256=hashlib.sha256(b"expected").hexdigest(),
            timeout_seconds=1,
        )

    assert target.read_bytes() == b"changed"
