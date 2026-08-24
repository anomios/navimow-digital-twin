"""Stable motion analysis for the Navimow digital twin.

Version 2.1 adds hysteresis and confirmation counters so semantic movement
events are not caused by a single noisy position sample.
"""
from __future__ import annotations

MODULE_NAME = "motion"
MODULE_VERSION = "2.1.0"
PROJECT_VERSION = "7.4.0"

from dataclasses import asdict, dataclass
import math
from typing import Any


def heading_cardinal(degrees: float | None) -> str:
    if degrees is None:
        return ""
    labels = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")
    return labels[int((degrees + 22.5) // 45.0) % 8]


@dataclass(slots=True)
class MotionState:
    speed_mps: float = 0.0
    acceleration_mps2: float = 0.0
    heading_degrees: float | None = None
    heading_cardinal: str = ""
    turn_rate_dps: float = 0.0
    motion: str = "unknown"
    moving: bool = False
    turning: bool = False
    distance_session_m: float = 0.0
    sample_interval_s: float = 0.0
    raw_distance_m: float = 0.0
    effective_distance_m: float = 0.0
    start_confirm_count: int = 0
    stop_confirm_count: int = 0

    def snapshot(self) -> dict[str, Any]:
        return asdict(self)


class MotionAnalyzer:
    """Derive stable movement information from successive map positions.

    The raw speed is still exposed immediately, while ``moving`` is a stable
    semantic state. Starting and stopping use different speed thresholds and
    must be confirmed over multiple consecutive samples.
    """

    def __init__(
        self,
        *,
        start_speed_mps: float = 0.08,
        stop_speed_mps: float = 0.025,
        noise_distance_m: float = 0.05,
        start_confirm_samples: int = 2,
        stop_confirm_samples: int = 3,
        turning_rate_dps: float = 8.0,
    ) -> None:
        self._start_speed_mps = max(0.0, float(start_speed_mps))
        self._stop_speed_mps = max(0.0, float(stop_speed_mps))
        if self._stop_speed_mps > self._start_speed_mps:
            raise ValueError("stop_speed_mps must not exceed start_speed_mps")

        self._noise_distance_m = max(0.0, float(noise_distance_m))
        self._start_confirm_samples = max(1, int(start_confirm_samples))
        self._stop_confirm_samples = max(1, int(stop_confirm_samples))
        self._turning_rate_dps = max(0.0, float(turning_rate_dps))

        self._last: tuple[float, float, float, float | None] | None = None
        self._stable_moving = False
        self._start_count = 0
        self._stop_count = 0
        self.state = MotionState()

    @staticmethod
    def _theta_to_degrees(theta: float | None) -> float | None:
        if theta is None:
            return None
        # Navimow posture theta: 0 points north; positive rotation is clockwise.
        return (math.degrees(theta) + 360.0) % 360.0

    @staticmethod
    def _angle_delta(current: float, previous: float) -> float:
        return (current - previous + 180.0) % 360.0 - 180.0

    def reset(self) -> None:
        """Discard samples and return to a clean standing state."""
        self._last = None
        self._stable_moving = False
        self._start_count = 0
        self._stop_count = 0
        self.state = MotionState()

    def _update_stable_state(self, speed: float) -> None:
        if self._stable_moving:
            self._start_count = 0
            if speed <= self._stop_speed_mps:
                self._stop_count += 1
                if self._stop_count >= self._stop_confirm_samples:
                    self._stable_moving = False
                    self._stop_count = 0
            else:
                self._stop_count = 0
        else:
            self._stop_count = 0
            if speed >= self._start_speed_mps:
                self._start_count += 1
                if self._start_count >= self._start_confirm_samples:
                    self._stable_moving = True
                    self._start_count = 0
            else:
                self._start_count = 0

    def update(
        self,
        x: float,
        y: float,
        theta: float | None,
        observed_at: float,
    ) -> MotionState:
        x = float(x)
        y = float(y)
        observed_at = float(observed_at)
        heading = self._theta_to_degrees(theta)

        if self._last is None:
            self._last = (x, y, observed_at, heading)
            self.state.heading_degrees = heading
            self.state.heading_cardinal = heading_cardinal(heading)
            self.state.motion = "standing"
            return self.state

        last_x, last_y, last_time, last_heading = self._last
        dt = max(0.0, observed_at - last_time)
        distance = math.hypot(x - last_x, y - last_y)
        effective_distance = distance if distance >= self._noise_distance_m else 0.0
        speed = effective_distance / dt if dt > 0.0 else 0.0

        previous_speed = self.state.speed_mps
        acceleration = (speed - previous_speed) / dt if dt > 0.0 else 0.0

        turn_rate = 0.0
        if heading is not None and last_heading is not None and dt > 0.0:
            turn_rate = self._angle_delta(heading, last_heading) / dt

        self._update_stable_state(speed)
        turning = self._stable_moving and abs(turn_rate) >= self._turning_rate_dps

        self.state.speed_mps = speed
        self.state.acceleration_mps2 = acceleration
        self.state.heading_degrees = heading
        self.state.heading_cardinal = heading_cardinal(heading)
        self.state.turn_rate_dps = turn_rate
        self.state.moving = self._stable_moving
        self.state.turning = turning
        self.state.motion = (
            "turning"
            if turning
            else ("moving" if self._stable_moving else "standing")
        )
        self.state.distance_session_m += effective_distance
        self.state.sample_interval_s = dt
        self.state.raw_distance_m = distance
        self.state.effective_distance_m = effective_distance
        self.state.start_confirm_count = self._start_count
        self.state.stop_confirm_count = self._stop_count

        self._last = (x, y, observed_at, heading)
        return self.state
