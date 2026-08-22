from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import yaml

from controlplane.models import RoutePolicy


class PolicyStore:
    """Resolve versioned policy packs and reload changed YAML files."""

    def __init__(self, policy_dir: Path) -> None:
        self.policy_dir = policy_dir
        self._cache: dict[str, tuple[int, dict[str, Any], str]] = {}

    def resolve(self, route: str, jurisdiction: str) -> RoutePolicy:
        modified_ns, pack, digest = self._load(jurisdiction)
        self._cache[jurisdiction] = (modified_ns, pack, digest)
        routes = pack.get("routes", {})
        if route not in routes:
            raise KeyError(f"Unknown route {route!r} for jurisdiction {jurisdiction!r}")

        defaults = dict(pack["defaults"])
        route_values = dict(routes[route])
        resolved = defaults | route_values
        return RoutePolicy(
            route=route,
            jurisdiction=str(pack["jurisdiction"]),
            policy_version=str(pack["version"]),
            policy_hash=digest,
            **resolved,
        )

    def _load(self, jurisdiction: str) -> tuple[int, dict[str, Any], str]:
        path = self.policy_dir / f"{jurisdiction}.yaml"
        if not path.exists():
            raise KeyError(f"No policy pack for jurisdiction {jurisdiction!r}")
        modified_ns = path.stat().st_mtime_ns
        cached = self._cache.get(jurisdiction)
        if cached is not None and cached[0] == modified_ns:
            return cached

        raw = path.read_bytes()
        loaded = yaml.safe_load(raw)
        if not isinstance(loaded, dict):
            raise ValueError(f"Policy pack {path} must be a mapping")
        digest = hashlib.sha256(raw).hexdigest()[:16]
        return modified_ns, loaded, digest
