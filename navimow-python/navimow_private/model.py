"""Digital-twin model for a Segway Navimow mower."""
from __future__ import annotations

MODULE_NAME = "model"
MODULE_VERSION = "2.0.0"
PROJECT_VERSION = "7.4.0"

from dataclasses import dataclass, asdict
import time
from typing import Any

from .geometry import GeometryState, NavimowGeometry
from .motion import MotionAnalyzer, MotionState


def _float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


@dataclass(slots=True)
class LocationState:
    latitude: float | None = None
    longitude: float | None = None
    x: float | None = None
    y: float | None = None
    theta: float | None = None
    report_time: str = ""


@dataclass(slots=True)
class TrailState:
    point_count: int = 0
    distance_m: float = 0.0
    active: bool = False
    filename: str = ""


class NavimowModel:
    """Aggregate raw private-cloud data into a stable mower state."""

    def __init__(self) -> None:
        self.location = LocationState()
        self.motion_analyzer = MotionAnalyzer()
        self.motion: MotionState = self.motion_analyzer.state
        self.geometry_engine = NavimowGeometry()
        self.geometry = GeometryState()
        self.trail = TrailState()
        self.motion_detail = "unknown"
        self.updated_at: float | None = None

    def _derive_motion_detail(self) -> None:
        if self.geometry.location_area == "dock" and not self.motion.moving:
            self.motion_detail = "docked"
        elif self.geometry.location_area == "tunnel" and self.motion.moving:
            self.motion_detail = "inTunnel"
        elif self.motion.turning:
            self.motion_detail = "turning"
        elif self.motion.moving:
            self.motion_detail = "moving"
        else:
            self.motion_detail = "standing"

    def update_geometry(self, geometry: dict[str, Any]) -> None:
        self.geometry_engine.load(geometry)
        if self.location.x is not None and self.location.y is not None:
            self.geometry = self.geometry_engine.analyse(self.location.x, self.location.y)
            self._derive_motion_detail()

    def update_location(self, data: dict[str, Any], *, observed_at: float | None = None) -> None:
        if not isinstance(data, dict):
            raise TypeError("location data must be a dictionary")
        observed_at = time.time() if observed_at is None else float(observed_at)

        self.location.latitude = _float(data.get("latitude"))
        self.location.longitude = _float(data.get("longitude"))
        self.location.x = _float(data.get("postureX"))
        self.location.y = _float(data.get("postureY"))
        self.location.theta = _float(data.get("postureTheta"))
        self.location.report_time = str(data.get("reportTime") or "")

        if self.location.x is not None and self.location.y is not None:
            self.motion = self.motion_analyzer.update(
                self.location.x,
                self.location.y,
                self.location.theta,
                observed_at,
            )
            self.geometry = self.geometry_engine.analyse(self.location.x, self.location.y)
            self._derive_motion_detail()

        try:
            point_count = int(data.get("trailPointCount") or 0)
        except (TypeError, ValueError):
            point_count = 0
        self.trail = TrailState(
            point_count=point_count,
            distance_m=float(data.get("trailDistance") or 0.0),
            active=bool(data.get("trailActive")),
            filename=str(data.get("trailFile") or ""),
        )
        self.updated_at = observed_at

    def snapshot(self) -> dict[str, Any]:
        return {
            "version": 2,
            "updated_at": self.updated_at,
            "location": asdict(self.location),
            "motion": self.motion.snapshot(),
            "motion_detail": self.motion_detail,
            "geometry": self.geometry.snapshot(),
            "trail": asdict(self.trail),
        }
