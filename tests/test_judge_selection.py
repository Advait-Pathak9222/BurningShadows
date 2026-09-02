"""Tier 2 is selectable, and an unreachable judge fails closed rather than clean."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
import yaml

from controlplane.detectors.judge_selection import (
    GuardedJudge,
    JudgeUnavailable,
    Tier2Settings,
    build_tier2,
)
from controlplane.detectors.ollama_judge import OllamaJudge
from controlplane.detectors.tier2_judge import Tier2Judge
from controlplane.models import DetectorSignal, HarmVector, Interaction

REPO = Path(__file__).resolve().parents[1]


def _interaction(response: str = "the account is definitely closed") -> Interaction:
    return Interaction(
        interaction_id="judge-test",
        route="support-assistant",
        jurisdiction="eu",
        prompt="what happened to my account",
        response=response,
        context_documents=[],
        split="calibration",
    )


def _root_with(tmp_path: Path, tier2: dict[str, object]) -> Path:
    """A repository root whose judge.yaml carries the given tier 2 section."""
    config = tmp_path / "config"
    config.mkdir(parents=True, exist_ok=True)
    shipped = yaml.safe_load((REPO / "config" / "judge.yaml").read_text(encoding="utf-8"))
    shipped["tier2"] = tier2
    (config / "judge.yaml").write_text(yaml.safe_dump(shipped), encoding="utf-8")
    return tmp_path


# --------------------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------------------


def test_the_shipped_default_is_the_stub() -> None:
    """A clean clone must run offline, and every committed figure used the stub."""
    settings = Tier2Settings.load(REPO / "config" / "judge.yaml")
    assert settings.provider == "stub"
    assert isinstance(build_tier2(REPO), Tier2Judge)


def test_a_missing_config_falls_back_to_the_stub(tmp_path: Path) -> None:
    assert Tier2Settings.load(tmp_path / "absent.yaml").provider == "stub"


def test_an_unknown_provider_is_refused(tmp_path: Path) -> None:
    root = _root_with(tmp_path, {"provider": "gpt-9"})
    with pytest.raises(ValueError, match="unknown tier 2 provider"):
        build_tier2(root)


def test_an_out_of_range_unavailable_score_is_refused(tmp_path: Path) -> None:
    root = _root_with(tmp_path, {"provider": "stub", "unavailable_score": 7})
    with pytest.raises(ValueError, match=r"\[0, 1\]"):
        build_tier2(root)


def test_selecting_ollama_builds_the_real_adapter(tmp_path: Path) -> None:
    root = _root_with(tmp_path, {"provider": "ollama", "probe_on_start": False})
    built = build_tier2(root, client=httpx.Client())
    assert isinstance(built, GuardedJudge)
    assert isinstance(built.inner, OllamaJudge)
    # The fingerprint has to name the scorer that ran, not the wrapper around it.
    assert built.name.startswith("tier2_ollama")


def test_an_unreachable_host_refuses_to_start(tmp_path: Path) -> None:
    """Discovering this on the first expensive request, after pricing it, is worse."""
    shipped = yaml.safe_load((REPO / "config" / "judge.yaml").read_text(encoding="utf-8"))
    shipped["host"] = "http://127.0.0.1:9"
    shipped["tier2"] = {"provider": "ollama", "probe_on_start": True}
    config = tmp_path / "config"
    config.mkdir(parents=True, exist_ok=True)
    (config / "judge.yaml").write_text(yaml.safe_dump(shipped), encoding="utf-8")
    with pytest.raises(JudgeUnavailable, match="no model answered"):
        build_tier2(tmp_path)


# --------------------------------------------------------------------------------------
# Failure is closed
# --------------------------------------------------------------------------------------


class _Exploding:
    name = "tier2_exploding"
    version = "1"
    tier = 2

    def run(self, interaction: Interaction) -> DetectorSignal:
        raise httpx.ConnectError("connection refused")


class _Working:
    name = "tier2_working"
    version = "1"
    tier = 2

    def run(self, interaction: Interaction) -> DetectorSignal:
        return DetectorSignal(
            name=self.name,
            tier=self.tier,
            scores=HarmVector(
                hallucination=0.3,
                pii_leak=0.2,
                bias=0.1,
                unsafe_content=0.05,
                injection_or_exfil=0.02,
            ),
            latency_ms=1.0,
            evidence=["scored"],
        )


def test_a_judge_that_dies_scores_closed_not_clean() -> None:
    """An assurance check that did not run is not a passing check."""
    guarded = GuardedJudge(_Exploding(), unavailable_score=1.0)
    signal = guarded.run(_interaction())
    assert signal.scores.maximum() == pytest.approx(1.0)
    assert all(
        getattr(signal.scores, axis) == pytest.approx(1.0)
        for axis in ("hallucination", "pii_leak", "bias", "unsafe_content", "injection_or_exfil")
    )
    assert "unavailable" in signal.evidence[0]
    assert "ConnectError" in signal.evidence[0]


def test_a_working_judge_passes_straight_through() -> None:
    guarded = GuardedJudge(_Working(), unavailable_score=1.0)
    signal = guarded.run(_interaction())
    assert signal.scores.hallucination == pytest.approx(0.3)
    assert signal.evidence == ["scored"]


def test_the_wrapper_keeps_the_inner_identity() -> None:
    """detector_fingerprint() must name the scorer, so a map cannot outlive it."""
    guarded = GuardedJudge(_Working(), unavailable_score=1.0)
    assert guarded.name == "tier2_working"
    assert guarded.version == "1"
    assert guarded.tier == 2
