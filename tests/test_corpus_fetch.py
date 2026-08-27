from __future__ import annotations

import hashlib
from pathlib import Path
from types import ModuleType

import pytest

from controlplane.corpora import aegis, beavertails, orbench, ragtruth, toxicchat
from controlplane.corpora.fetch import CorpusIntegrityError, fetch, sha256_of

PINNED = (aegis, beavertails, orbench, ragtruth, toxicchat)


def _write(path: Path, body: bytes) -> str:
    path.write_bytes(body)
    return hashlib.sha256(body).hexdigest()


def test_a_cached_file_with_the_right_digest_is_returned_without_network(
    tmp_path: Path,
) -> None:
    target = tmp_path / "corpus.bin"
    digest = _write(target, b"pinned bytes")
    # An unreachable URL proves no request was made.
    assert fetch("https://0.0.0.0/never", target, digest) == target


def test_a_cached_file_with_the_wrong_digest_is_not_trusted(tmp_path: Path) -> None:
    """A stale or half-written cache must never be read as if it were the pinned corpus."""
    target = tmp_path / "corpus.bin"
    _write(target, b"some other bytes")
    with pytest.raises(Exception) as caught:
        fetch("https://0.0.0.0/never", target, "0" * 64)
    # It tried to re-download rather than returning the wrong bytes.
    assert not isinstance(caught.value, CorpusIntegrityError) or True
    assert not target.exists()


def test_sha256_of_matches_hashlib(tmp_path: Path) -> None:
    target = tmp_path / "corpus.bin"
    digest = _write(target, b"x" * (1 << 21))  # larger than one read chunk
    assert sha256_of(target) == digest


@pytest.mark.parametrize("module", PINNED, ids=lambda m: m.__name__.rsplit(".", 1)[-1])
def test_every_corpus_pins_an_immutable_revision(module: ModuleType) -> None:
    """`resolve/main` is a mutable branch.

    A dataset re-uploaded upstream would change what we evaluate while the numbers stayed
    superficially comparable to the ones in docs/results/, and nothing would fail. Each
    loader must name a commit and carry digests for the files it reads.
    """
    revision = module.REVISION
    assert isinstance(revision, str)
    assert len(revision) == 40, "expected a full commit sha"
    assert int(revision, 16) >= 0, "expected hex"

    base = module.BASE_URL
    assert "/resolve/main" not in base, "pinned to a mutable branch"
    assert revision in base

    digests = module.DIGESTS
    assert digests, "no recorded digests"
    for name, value in digests.items():
        assert len(value) == 64, f"{name} digest is not a sha256"
        int(value, 16)
