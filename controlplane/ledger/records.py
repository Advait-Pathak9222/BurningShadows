from __future__ import annotations

import json

from controlplane.models import DecisionTrace


def canonical_record(trace: DecisionTrace) -> str:
    return json.dumps(trace.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
