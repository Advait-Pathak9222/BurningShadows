from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from controlplane.models import HarmVector, Interaction
from controlplane.runtime import (
    AdmissionController,
    AdmissionMode,
    AdmissionRejected,
    LaneLimits,
    RouteAdmissionLimits,
    RuntimeLimits,
)
from controlplane.service import AssessmentEngine


def _controller(*, queue_capacity: int = 0, timeout_ms: float = 20.0) -> AdmissionController:
    discretionary = LaneLimits(
        concurrency=1,
        queue_capacity=queue_capacity,
        rate_per_second=10_000.0,
        burst=20,
        queue_timeout_ms=timeout_ms,
    )
    mandatory = LaneLimits(
        concurrency=1,
        queue_capacity=0,
        rate_per_second=10_000.0,
        burst=20,
        queue_timeout_ms=timeout_ms,
    )
    limits = RuntimeLimits(
        version="test",
        routes={
            "support-assistant": RouteAdmissionLimits(
                discretionary=discretionary,
                mandatory=mandatory,
            )
        },
    )
    return AdmissionController(limits)


def test_pressure_uses_reserved_lane_before_rejecting() -> None:
    async def scenario() -> None:
        controller = _controller()
        normal = await controller.admit("support-assistant")
        degraded = await controller.admit("support-assistant")

        assert normal.mode == AdmissionMode.NORMAL
        assert degraded.mode == AdmissionMode.DEGRADED
        with pytest.raises(AdmissionRejected):
            await controller.admit("support-assistant")

        snapshot = controller.snapshot()["routes"]["support-assistant"]
        assert snapshot["normal"] == 1
        assert snapshot["degraded"] == 1
        assert snapshot["rejected"] == 1
        normal.release()
        degraded.release()

    asyncio.run(scenario())


def test_bounded_queue_never_exceeds_its_limit() -> None:
    async def scenario() -> None:
        controller = _controller(queue_capacity=1, timeout_ms=500.0)
        active = await controller.admit("support-assistant")
        queued_task = asyncio.create_task(controller.admit("support-assistant"))
        for _ in range(100):
            snapshot = controller.snapshot()["routes"]["support-assistant"]
            if snapshot["discretionary"]["queued"] == 1:
                break
            await asyncio.sleep(0)
        else:
            pytest.fail("request did not enter the bounded queue")

        degraded = await controller.admit("support-assistant")
        with pytest.raises(AdmissionRejected):
            await controller.admit("support-assistant")
        snapshot = controller.snapshot()["routes"]["support-assistant"]
        assert snapshot["discretionary"]["max_queued"] == 1

        active.release()
        queued = await queued_task
        queued.release()
        degraded.release()

    asyncio.run(scenario())


def test_degraded_assessment_keeps_floor_and_skips_tier_two(project_root: Path) -> None:
    engine = AssessmentEngine(
        project_root,
        conformal_thresholds={"finops-agent": 0.1},
    )
    interaction = Interaction(
        interaction_id="runtime-floor",
        split="scenario",
        route="finops-agent",
        prompt="Summarise the vendor review.",
        response="The vendor definitely passed every security review in 2026.",
        truth=HarmVector.zeros(),
    )

    normal = engine.assess(interaction)
    degraded = engine.assess(
        interaction,
        mandatory_only=True,
        admission_mode="degraded",
        queue_wait_ms=3.0,
    )

    assert normal.selected_tier == 2
    assert degraded.selected_tier == 1
    assert degraded.forced_by_conformal is True
    assert degraded.degraded is True
    assert degraded.mandatory_assessment_completed is True
    assert degraded.queue_wait_ms == 3.0
