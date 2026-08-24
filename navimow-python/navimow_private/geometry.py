"""Map geometry queries for the Navimow digital twin."""
from __future__ import annotations

MODULE_NAME = "geometry"
MODULE_VERSION = "2.1.0"
PROJECT_VERSION = "7.4.0"

from dataclasses import dataclass, asdict
import math
from typing import Any, Iterable

Point = tuple[float, float]


def _points(raw: Any) -> list[Point]:
    result: list[Point] = []
    if not isinstance(raw, list):
        return result
    for item in raw:
        if isinstance(item, (list, tuple)) and len(item) >= 2:
            try:
                result.append((float(item[0]), float(item[1])))
            except (TypeError, ValueError):
                pass
    return result


def point_in_polygon(x: float, y: float, polygon: Iterable[Point]) -> bool:
    points = list(polygon)
    if len(points) < 3:
        return False
    inside = False
    j = len(points) - 1
    for i, (xi, yi) in enumerate(points):
        xj, yj = points[j]
        crosses = (yi > y) != (yj > y)
        if crosses:
            denominator = yj - yi
            x_cross = (xj - xi) * (y - yi) / denominator + xi
            if x < x_cross:
                inside = not inside
        j = i
    return inside


def distance_to_segment(x: float, y: float, a: Point, b: Point) -> float:
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    length_sq = dx * dx + dy * dy
    if length_sq == 0.0:
        return math.hypot(x - ax, y - ay)
    t = max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / length_sq))
    px, py = ax + t * dx, ay + t * dy
    return math.hypot(x - px, y - py)


def distance_to_polyline(x: float, y: float, points: list[Point]) -> float | None:
    if not points:
        return None
    if len(points) == 1:
        return math.hypot(x - points[0][0], y - points[0][1])
    return min(distance_to_segment(x, y, points[i - 1], points[i]) for i in range(1, len(points)))


def bearing_degrees(x: float, y: float, target_x: float, target_y: float) -> float:
    """Bearing in map coordinates: 0° east, 90° north."""
    return (math.degrees(math.atan2(target_y - y, target_x - x)) + 360.0) % 360.0


def cardinal(degrees: float | None) -> str:
    if degrees is None:
        return ""
    labels = ("E", "NE", "N", "NW", "W", "SW", "S", "SE")
    return labels[int((degrees + 22.5) // 45.0) % 8]


@dataclass(slots=True)
class GeometryState:
    location_area: str = "unknown"
    current_zone_id: str = ""
    current_zone_name: str = ""
    inside_boundary: bool = False
    in_tunnel: bool = False
    tunnel_id: str = ""
    dock_distance_m: float | None = None
    dock_bearing_degrees: float | None = None
    dock_bearing_cardinal: str = ""
    near_dock: bool = False

    def snapshot(self) -> dict[str, Any]:
        return asdict(self)


class NavimowGeometry:
    def __init__(self, geometry: dict[str, Any] | None = None, *, tunnel_tolerance_m: float = 0.45, near_dock_m: float = 1.25) -> None:
        self._geometry: dict[str, Any] = geometry or {}
        self._loaded = bool(geometry)
        self._tunnel_tolerance_m = float(tunnel_tolerance_m)
        self._near_dock_m = float(near_dock_m)

    def load(self, geometry: dict[str, Any]) -> None:
        self._geometry = geometry if isinstance(geometry, dict) else {}
        self._loaded = bool(self._geometry)

    def analyse(self, x: float, y: float) -> GeometryState:
        state = GeometryState()
        x, y = float(x), float(y)

        for zone in self._geometry.get("zones") or []:
            if not isinstance(zone, dict):
                continue
            for boundary in zone.get("boundaries") or []:
                if not isinstance(boundary, dict):
                    continue
                if point_in_polygon(x, y, _points(boundary.get("points"))):
                    state.current_zone_id = str(zone.get("id") or "")
                    state.current_zone_name = str(zone.get("name") or boundary.get("name") or "")
                    state.inside_boundary = True
                    break
            if state.inside_boundary:
                break

        best_tunnel: tuple[float, str] | None = None
        for tunnel in self._geometry.get("tunnels") or []:
            if not isinstance(tunnel, dict):
                continue
            distance = distance_to_polyline(x, y, _points(tunnel.get("points")))
            if distance is not None and (best_tunnel is None or distance < best_tunnel[0]):
                best_tunnel = (distance, str(tunnel.get("id") or ""))
        if best_tunnel is not None and best_tunnel[0] <= self._tunnel_tolerance_m:
            state.in_tunnel = True
            state.tunnel_id = best_tunnel[1]

        best_dock: tuple[float, Point] | None = None
        for dock in self._geometry.get("docks") or []:
            if not isinstance(dock, dict):
                continue
            # ``position`` is the physical charging-pile reference.  The
            # ``navPosition`` lies in front of the pile and is intended as an
            # approach/navigation point.  Using it as the dock itself made the
            # mower appear about one metre away while it was physically docked.
            raw = dock.get("position") or dock.get("navPosition")
            pts = _points([raw])
            if pts:
                point = pts[0]
                distance = math.hypot(x - point[0], y - point[1])
                if best_dock is None or distance < best_dock[0]:
                    best_dock = (distance, point)
        if best_dock is not None:
            state.dock_distance_m = best_dock[0]
            state.near_dock = state.dock_distance_m <= self._near_dock_m
            state.dock_bearing_degrees = bearing_degrees(x, y, best_dock[1][0], best_dock[1][1])
            state.dock_bearing_cardinal = cardinal(state.dock_bearing_degrees)

        # Semantic context priority:
        #
        #   tunnel > zone > dock > outside > unknown
        #
        # ``near_dock`` is only a distance flag.  It must not hide a real zone
        # or tunnel match while the mower is leaving or approaching the dock.
        # A loaded map without any match is a known outside position.
        if state.in_tunnel:
            state.location_area = "tunnel"
        elif state.current_zone_id:
            state.location_area = "zone"
        elif state.near_dock:
            state.location_area = "dock"
        elif self._loaded:
            state.location_area = "outside"

        return state
