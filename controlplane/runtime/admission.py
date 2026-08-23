from __future__ import annotations

import asyncio
import threading
import time
from enum import StrEnum
from pathlib import Path
from typing import Any, Final

import yaml
from pydantic import BaseModel, ConfigDict, Field


class AdmissionMode(StrEnum):
    NORMAL = "normal"
    DEGRADED = "degraded"


class LaneLimits(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    concurrency: int = Field(gt=0)
    queue_capacity: int = Field(ge=0)
    rate_per_second: float = Field(gt=0.0)
    burst: int = Field(gt=0)
    queue_timeout_ms: float = Field(gt=0.0)


class RouteAdmissionLimits(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    discretionary: LaneLimits
    mandatory: LaneLimits


class RuntimeLimits(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    version: str
    routes: dict[str, RouteAdmissionLimits]

    @classmethod
    def load(cls, path: Path) -> RuntimeLimits:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            raise ValueError("Runtime config must be a mapping")
        return cls.model_validate(loaded)


class AdmissionRejected(RuntimeError):
    def __init__(self, route: str) -> None:
        super().__init__(f"Runtime capacity exhausted for route {route!r}")
        self.route = route


class _TokenBucket:
    def __init__(self, rate_per_second: float, burst: int) -> None:
        self._rate = rate_per_second
        self._capacity = float(burst)
        self._tokens = float(burst)
        self._updated = time.monotonic()
        self._lock = threading.Lock()

    def consume(self) -> bool:
        now = time.monotonic()
        with self._lock:
            elapsed = max(0.0, now - self._updated)
            self._tokens = min(self._capacity, self._tokens + elapsed * self._rate)
            self._updated = now
            if self._tokens < 1.0:
                return False
            self._tokens -= 1.0
            return True


class _BoundedLane:
    def __init__(self, limits: LaneLimits) -> None:
        self.limits = limits
        self._semaphore = asyncio.Semaphore(limits.concurrency)
        self.active = 0
        self.queued = 0
        self.max_active = 0
        self.max_queued = 0

    async def acquire(self) -> float | None:
        started = time.perf_counter_ns()
        if not self._semaphore.locked():
            await self._semaphore.acquire()
            self._mark_active()
            return _elapsed_ms(started)
        if self.queued >= self.limits.queue_capacity:
            return None

        self.queued += 1
        self.max_queued = max(self.max_queued, self.queued)
        try:
            timeout_s = self.limits.queue_timeout_ms / 1000.0
            await asyncio.wait_for(self._semaphore.acquire(), timeout=timeout_s)
        except TimeoutError:
            return None
        finally:
            self.queued -= 1
        self._mark_active()
        return _elapsed_ms(started)

    def release(self) -> None:
        if self.active <= 0:
            raise RuntimeError("Admission lane released without an active lease")
        self.active -= 1
        self._semaphore.release()

    def snapshot(self) -> dict[str, int]:
        return {
            "active": self.active,
            "queued": self.queued,
            "max_active": self.max_active,
            "max_queued": self.max_queued,
        }

    def _mark_active(self) -> None:
        self.active += 1
        self.max_active = max(self.max_active, self.active)


class AdmissionLease:
    def __init__(
        self,
        route: str,
        mode: AdmissionMode,
        queue_wait_ms: float,
        lane: _BoundedLane,
    ) -> None:
        self.route = route
        self.mode = mode
        self.queue_wait_ms = queue_wait_ms
        self._lane = lane
        self._released = False

    @property
    def degraded(self) -> bool:
        return self.mode == AdmissionMode.DEGRADED

    def release(self) -> None:
        if not self._released:
            self._lane.release()
            self._released = True


class _RouteState:
    def __init__(self, limits: RouteAdmissionLimits) -> None:
        self.discretionary = _BoundedLane(limits.discretionary)
        self.mandatory = _BoundedLane(limits.mandatory)
        self.discretionary_tokens = _TokenBucket(
            limits.discretionary.rate_per_second,
            limits.discretionary.burst,
        )
        self.mandatory_tokens = _TokenBucket(
            limits.mandatory.rate_per_second,
            limits.mandatory.burst,
        )
        self.normal = 0
        self.degraded = 0
        self.rejected = 0


class AdmissionController:
    """Reserve capacity for the mandatory floor when discretionary work backs up."""

    _LANES: Final = (
        (AdmissionMode.NORMAL, "discretionary"),
        (AdmissionMode.DEGRADED, "mandatory"),
    )

    def __init__(self, limits: RuntimeLimits) -> None:
        self.limits = limits
        self._routes = {
            route: _RouteState(route_limits) for route, route_limits in limits.routes.items()
        }

    @classmethod
    def from_path(cls, path: Path) -> AdmissionController:
        return cls(RuntimeLimits.load(path))

    async def admit(self, route: str) -> AdmissionLease:
        if route not in self._routes:
            raise KeyError(f"Unknown route {route!r} for runtime admission")
        started = time.perf_counter_ns()
        state = self._routes[route]
        for mode, lane_name in self._LANES:
            lane = getattr(state, lane_name)
            bucket = getattr(state, f"{lane_name}_tokens")
            lease = await self._try_lane(route, mode, lane, bucket)
            if lease is not None:
                lease.queue_wait_ms = _elapsed_ms(started)
                if mode == AdmissionMode.NORMAL:
                    state.normal += 1
                else:
                    state.degraded += 1
                return lease
        state.rejected += 1
        raise AdmissionRejected(route)

    def snapshot(self) -> dict[str, Any]:
        routes: dict[str, Any] = {}
        for route, state in self._routes.items():
            routes[route] = {
                "normal": state.normal,
                "degraded": state.degraded,
                "rejected": state.rejected,
                "discretionary": state.discretionary.snapshot(),
                "mandatory": state.mandatory.snapshot(),
            }
        return {"version": self.limits.version, "routes": routes}

    @staticmethod
    async def _try_lane(
        route: str,
        mode: AdmissionMode,
        lane: _BoundedLane,
        bucket: _TokenBucket,
    ) -> AdmissionLease | None:
        if not bucket.consume():
            return None
        wait_ms = await lane.acquire()
        if wait_ms is None:
            return None
        return AdmissionLease(route, mode, wait_ms, lane)


def _elapsed_ms(started_ns: int) -> float:
    return (time.perf_counter_ns() - started_ns) / 1_000_000.0
