"""Choose which detector serves tier 2, and refuse to pretend when it cannot run.

Until now `Tier2Judge`, a deterministic string matcher, was the only thing the serving path
could use. `OllamaJudge` existed, had tests, and was measured by `make judge-probe`, but no
route could actually buy it. That gap is the difference between a design result and a measured
one, and it is what this module closes.

The default stays the stub, deliberately. `make demo` has to run from a clean clone with no
key, no network and no local model, and every committed figure was produced against the stub.
Switching provider changes `detector_fingerprint()`, which invalidates any released
calibration artifact fitted against the old scorers rather than silently serving it.

**Failure is closed, not open.** A judge the allocator paid for and did not receive is not a
clean result. If the model is unreachable mid-request the wrapper returns the configured
unavailable vector, which is 1.0 on every axis by default, so the conformal floor forces the
safe action instead of letting an unverified answer through carrying a spend record for a
check that never ran. The evidence line says so, and the trace keeps it.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any

import httpx
import yaml

from controlplane.detectors.base import Detector
from controlplane.detectors.ollama_judge import JudgeConfig, OllamaJudge
from controlplane.detectors.tier2_judge import Tier2Judge
from controlplane.models import DetectorSignal, HarmVector, Interaction

PROVIDERS = ("stub", "ollama")
DEFAULT_UNAVAILABLE_SCORE = 1.0


class JudgeUnavailable(RuntimeError):
    """The configured judge could not be reached at startup."""


@dataclass(frozen=True)
class Tier2Settings:
    provider: str
    unavailable_score: float
    probe_on_start: bool

    @classmethod
    def load(cls, path: Path) -> Tier2Settings:
        raw: dict[str, Any] = {}
        if path.exists():
            loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                raw = loaded
        section = raw.get("tier2") or {}
        if not isinstance(section, dict):
            raise ValueError("config/judge.yaml key 'tier2' must be a mapping")
        provider = str(section.get("provider", "stub")).strip().lower()
        if provider not in PROVIDERS:
            raise ValueError(
                f"unknown tier 2 provider {provider!r}, expected one of {list(PROVIDERS)}"
            )
        score = float(section.get("unavailable_score", DEFAULT_UNAVAILABLE_SCORE))
        if not 0.0 <= score <= 1.0:
            raise ValueError(f"tier2.unavailable_score must sit in [0, 1], found {score}")
        return cls(
            provider=provider,
            unavailable_score=score,
            probe_on_start=bool(section.get("probe_on_start", True)),
        )


class GuardedJudge(Detector):
    """Wrap a judge so an unreachable model fails closed and says that it did.

    The wrapper keeps the wrapped judge's name and version, because the fingerprint has to
    identify the scorer that actually ran, not the wrapper around it.
    """

    tier = 2

    def __init__(self, inner: Detector, unavailable_score: float) -> None:
        self.inner = inner
        self.unavailable_score = unavailable_score
        self.name = getattr(inner, "name", "tier2_judge")
        self.version = getattr(inner, "version", "1")

    def run(self, interaction: Interaction) -> DetectorSignal:
        started = perf_counter()
        try:
            return self.inner.run(interaction)
        except Exception as error:  # noqa: BLE001 - any failure is an unrun check
            worst = self.unavailable_score
            return DetectorSignal(
                name=self.name,
                tier=self.tier,
                scores=HarmVector(
                    hallucination=worst,
                    pii_leak=worst,
                    bias=worst,
                    unsafe_content=worst,
                    injection_or_exfil=worst,
                ),
                latency_ms=(perf_counter() - started) * 1000.0,
                evidence=[
                    "tier 2 judge unavailable, scored closed rather than clean: "
                    f"{type(error).__name__}: {str(error)[:160]}"
                ],
            )


def _reachable(host: str, timeout: float = 5.0) -> bool:
    try:
        response = httpx.get(f"{host.rstrip('/')}/api/tags", timeout=timeout)
    except httpx.HTTPError:
        return False
    return response.status_code == 200


def build_tier2(root: Path, *, client: httpx.Client | None = None) -> Detector:
    """The tier 2 detector this deployment is configured to serve.

    Raises `JudgeUnavailable` at construction rather than at request time when a real judge
    is configured and its host is not answering. Discovering that on the first expensive
    request, after the allocator has already priced it, is strictly worse than refusing to
    start.
    """
    config_path = root / "config" / "judge.yaml"
    settings = Tier2Settings.load(config_path)
    if settings.provider == "stub":
        return Tier2Judge()

    judge_config = JudgeConfig.load(config_path)
    if settings.probe_on_start and client is None and not _reachable(judge_config.host):
        raise JudgeUnavailable(
            f"tier2.provider is {settings.provider!r} but no model answered at "
            f"{judge_config.host}. Start it with `ollama serve` and "
            f"`ollama pull {judge_config.model}`, or set tier2.provider back to 'stub' "
            f"in {config_path}."
        )
    return GuardedJudge(
        OllamaJudge(judge_config, client=client), settings.unavailable_score
    )
