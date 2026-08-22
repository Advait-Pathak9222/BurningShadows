from __future__ import annotations

import hashlib

GENESIS_HASH = "0" * 64


def record_hash(previous_hash: str, canonical_record: str) -> str:
    payload = f"{previous_hash}|{canonical_record}".encode()
    return hashlib.sha256(payload).hexdigest()
