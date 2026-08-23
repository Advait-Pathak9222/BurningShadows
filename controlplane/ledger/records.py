from __future__ import annotations

import json
from typing import Any

from controlplane.models import DecisionTrace, ReviewRecord


def canonical_record(trace: DecisionTrace) -> str:
    return _canonical("decision", trace.model_dump(mode="json"))


def canonical_review(record: ReviewRecord) -> str:
    return _canonical("review", record.model_dump(mode="json"))


def _canonical(kind: str, payload: dict[str, Any]) -> str:
    """Stamp the record kind so one chain can carry decisions and the reviews of them."""
    return json.dumps({"kind": kind} | payload, sort_keys=True, separators=(",", ":"))
