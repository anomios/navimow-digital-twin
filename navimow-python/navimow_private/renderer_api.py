#!/usr/bin/env python3
# -*- coding: utf-8 -*-

##############################################################################
#
# Navimow Digital Twin
#
# Module      : renderer_api.py
# Version     : 1.2.0
# Project     : 7.8.43
# Created     : 2026-08-03
# Last Change : 2026-08-08
#
# Description :
# Stable, renderer-neutral frame API for live view, replay and future
# visualizations of the Navimow Digital Twin.
#
# Public API  :
# Point2D
# RendererZone
# RendererTunnel
# RendererDock
# RendererMower
# RendererFrame
# build_renderer_frame()
# module_info()
#
# Change History
# --------------
#
# 1.2.0  2026-08-08
#   Added:
#     - No-go/obstacle polygons
#     - No-vision fence polygons
#
# 1.1.0  2026-08-06
#   Added:
#     - Trail points in RendererFrame
#     - Optional trail input for build_renderer_frame()
#
# 1.0.0  2026-08-03
#   Added:
#     - Initial renderer-neutral frame model
#     - Conversion from model snapshot and raw map geometry
#     - Immutable render data classes
#     - Defensive dictionary export
#
##############################################################################

"""Renderer-neutral frame model for Navimow visualizations."""
from __future__ import annotations

from copy import deepcopy
import math
from dataclasses import asdict, dataclass
from typing import Any, Iterable

MODULE_NAME = "renderer_api"
MODULE_VERSION = "1.4.0"
PROJECT_VERSION = "7.8.43"


def module_info() -> dict[str, str]:
    return {
        "module": MODULE_NAME,
        "version": MODULE_VERSION,
        "project": PROJECT_VERSION,
        "description": "Renderer-neutral frame API for Navimow visualizations",
    }


def _float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


@dataclass(slots=True, frozen=True)
class Point2D:
    x: float
    y: float

    def as_dict(self) -> dict[str, float]:
        return {"x": self.x, "y": self.y}


@dataclass(slots=True, frozen=True)
class RendererZone:
    zone_id: str
    name: str
    polygons: tuple[tuple[Point2D, ...], ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "zoneId": self.zone_id,
            "name": self.name,
            "polygons": [
                [point.as_dict() for point in polygon]
                for polygon in self.polygons
            ],
        }


@dataclass(slots=True, frozen=True)
class RendererTunnel:
    tunnel_id: str
    points: tuple[Point2D, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "tunnelId": self.tunnel_id,
            "points": [point.as_dict() for point in self.points],
        }


@dataclass(slots=True, frozen=True)
class RendererArea:
    area_id: str
    name: str
    points: tuple[Point2D, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "areaId": self.area_id,
            "name": self.name,
            "points": [point.as_dict() for point in self.points],
        }


@dataclass(slots=True, frozen=True)
class RendererDock:
    dock_id: str
    position: Point2D | None
    navigation_position: Point2D | None
    heading_degrees: float | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "dockId": self.dock_id,
            "position": None if self.position is None else self.position.as_dict(),
            "navigationPosition": (
                None
                if self.navigation_position is None
                else self.navigation_position.as_dict()
            ),
            "headingDegrees": self.heading_degrees,
        }


@dataclass(slots=True, frozen=True)
class RendererMower:
    position: Point2D | None
    heading_degrees: float | None
    motion: str
    motion_detail: str
    speed_mps: float
    location_area: str
    zone_id: str
    zone_name: str
    in_tunnel: bool
    near_dock: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "position": None if self.position is None else self.position.as_dict(),
            "headingDegrees": self.heading_degrees,
            "motion": self.motion,
            "motionDetail": self.motion_detail,
            "speedMps": self.speed_mps,
            "locationArea": self.location_area,
            "zoneId": self.zone_id,
            "zoneName": self.zone_name,
            "inTunnel": self.in_tunnel,
            "nearDock": self.near_dock,
        }


@dataclass(slots=True, frozen=True)
class RendererFrame:
    timestamp: float | None
    mower: RendererMower
    zones: tuple[RendererZone, ...]
    tunnels: tuple[RendererTunnel, ...]
    no_go_areas: tuple[RendererArea, ...]
    vision_off_areas: tuple[RendererArea, ...]
    docks: tuple[RendererDock, ...]
    trail: tuple[tuple[Point2D, ...], ...]
    metadata: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "version": 1,
            "timestamp": self.timestamp,
            "mower": self.mower.as_dict(),
            "zones": [zone.as_dict() for zone in self.zones],
            "tunnels": [tunnel.as_dict() for tunnel in self.tunnels],
            "noGoAreas": [area.as_dict() for area in self.no_go_areas],
            "visionOffAreas": [area.as_dict() for area in self.vision_off_areas],
            "docks": [dock.as_dict() for dock in self.docks],
            "trail": [[point.as_dict() for point in segment] for segment in self.trail],
            "metadata": deepcopy(self.metadata),
        }


def _point(raw: Any) -> Point2D | None:
    if not isinstance(raw, (list, tuple)) or len(raw) < 2:
        return None
    x = _float(raw[0])
    y = _float(raw[1])
    if x is None or y is None:
        return None
    return Point2D(x=x, y=y)


def _points(raw: Any) -> tuple[Point2D, ...]:
    if not isinstance(raw, list):
        return ()
    result: list[Point2D] = []
    for item in raw:
        point = _point(item)
        if point is not None:
            result.append(point)
    return tuple(result)



def _trail_segments(raw: Any) -> tuple[tuple[Point2D, ...], ...]:
    if isinstance(raw, dict):
        raw_points = raw.get("points") or []
        raw_breaks = raw.get("breaks") or []
    else:
        raw_points = raw if isinstance(raw, list) else []
        raw_breaks = []
    points = _points(raw_points)
    if not points:
        return ()
    breaks = []
    for value in raw_breaks:
        try:
            idx = int(value)
        except (TypeError, ValueError):
            continue
        if 0 < idx < len(points):
            breaks.append(idx)
    breaks = sorted(set(breaks))
    result = []
    start = 0
    for stop in breaks + [len(points)]:
        segment = tuple(points[start:stop])
        if segment:
            result.append(segment)
        start = stop
    return tuple(result)


def _zones(raw_geometry: dict[str, Any]) -> tuple[RendererZone, ...]:
    zones: list[RendererZone] = []

    for raw_zone in raw_geometry.get("zones") or []:
        if not isinstance(raw_zone, dict):
            continue

        polygons: list[tuple[Point2D, ...]] = []
        for boundary in raw_zone.get("boundaries") or []:
            if not isinstance(boundary, dict):
                continue
            polygon = _points(boundary.get("points"))
            if polygon:
                polygons.append(polygon)

        if not polygons:
            continue

        zones.append(
            RendererZone(
                zone_id=str(raw_zone.get("id") or ""),
                name=str(raw_zone.get("name") or ""),
                polygons=tuple(polygons),
            )
        )

    return tuple(zones)


def _tunnels(raw_geometry: dict[str, Any]) -> tuple[RendererTunnel, ...]:
    tunnels: list[RendererTunnel] = []

    for raw_tunnel in raw_geometry.get("tunnels") or []:
        if not isinstance(raw_tunnel, dict):
            continue
        points = _points(raw_tunnel.get("points"))
        if not points:
            continue
        tunnels.append(
            RendererTunnel(
                tunnel_id=str(raw_tunnel.get("id") or ""),
                points=points,
            )
        )

    return tuple(tunnels)


def _areas(
    raw_geometry: dict[str, Any],
    key: str,
) -> tuple[RendererArea, ...]:
    result: list[RendererArea] = []
    for raw_area in raw_geometry.get(key) or []:
        if not isinstance(raw_area, dict):
            continue
        points = _points(raw_area.get("points"))
        if not points:
            continue
        result.append(
            RendererArea(
                area_id=str(raw_area.get("id") or ""),
                name=str(raw_area.get("name") or ""),
                points=points,
            )
        )
    return tuple(result)


def _docks(raw_geometry: dict[str, Any]) -> tuple[RendererDock, ...]:
    docks: list[RendererDock] = []

    for raw_dock in raw_geometry.get("docks") or []:
        if not isinstance(raw_dock, dict):
            continue

        heading = _float(
            raw_dock.get("heading")
            if raw_dock.get("heading") is not None
            else raw_dock.get("theta")
        )

        if heading is None:
            direction = _float(raw_dock.get("direction"))
            if direction is not None:
                heading = math.degrees(direction)

        if heading is None:
            dock_pos = _point(raw_dock.get("position"))
            nav_pos = _point(raw_dock.get("navPosition"))
            if dock_pos is not None and nav_pos is not None:
                dx = nav_pos.x - dock_pos.x
                dy = nav_pos.y - dock_pos.y
                if dx != 0.0 or dy != 0.0:
                    heading = math.degrees(math.atan2(dy, dx))

        docks.append(
            RendererDock(
                dock_id=str(raw_dock.get("id") or ""),
                position=_point(raw_dock.get("position")),
                navigation_position=_point(raw_dock.get("navPosition")),
                heading_degrees=heading,
            )
        )

    return tuple(docks)


def build_renderer_frame(
    snapshot: dict[str, Any],
    raw_geometry: dict[str, Any] | None = None,
    *,
    trail: Any = None,
    metadata: dict[str, Any] | None = None,
    force_docked: bool = False,
) -> RendererFrame:
    """Build one immutable renderer frame.

    ``snapshot`` is the nested result of ``NavimowModel.snapshot()``.
    ``raw_geometry`` is the private map geometry returned by the Navimow API.
    """
    if not isinstance(snapshot, dict):
        raise TypeError("snapshot must be a dictionary")

    raw_geometry = raw_geometry if isinstance(raw_geometry, dict) else {}
    location = snapshot.get("location") or {}
    motion = snapshot.get("motion") or {}
    geometry_state = snapshot.get("geometry") or {}

    x = _float(location.get("x"))
    y = _float(location.get("y"))
    mower_position = None if x is None or y is None else Point2D(x=x, y=y)

    heading = _float(motion.get("heading_degrees"))
    if heading is None:
        theta = _float(location.get("theta"))
        if theta is not None:
            # Theta is retained as a fallback only. The MotionAnalyzer normally
            # provides the renderer-ready heading in degrees.
            heading = theta

    renderer_docks = _docks(raw_geometry)

    motion_detail = str(snapshot.get("motion_detail") or "unknown")
    location_area = str(geometry_state.get("location_area") or "unknown")

    if (
        force_docked
        or motion_detail.lower() == "docked"
        or location_area.lower() == "dock"
    ):
        dock = next((item for item in renderer_docks if item.position is not None), None)
        if dock is not None:
            mower_position = dock.position
            if dock.heading_degrees is not None:
                heading = dock.heading_degrees

    mower = RendererMower(
        position=mower_position,
        heading_degrees=heading,
        motion=str(motion.get("motion") or "unknown"),
        motion_detail=motion_detail,
        speed_mps=float(_float(motion.get("speed_mps")) or 0.0),
        location_area=location_area,
        zone_id=str(geometry_state.get("current_zone_id") or ""),
        zone_name=str(geometry_state.get("current_zone_name") or ""),
        in_tunnel=bool(geometry_state.get("in_tunnel")),
        near_dock=bool(geometry_state.get("near_dock")),
    )

    frame_metadata = {
        "snapshotVersion": snapshot.get("version"),
        "rendererApiVersion": MODULE_VERSION,
    }
    if metadata:
        frame_metadata.update(deepcopy(metadata))

    return RendererFrame(
        timestamp=_float(snapshot.get("updated_at")),
        mower=mower,
        zones=_zones(raw_geometry),
        tunnels=_tunnels(raw_geometry),
        no_go_areas=_areas(raw_geometry, "obstacles"),
        vision_off_areas=_areas(raw_geometry, "visionOffAreas"),
        docks=renderer_docks,
        trail=_trail_segments(trail),
        metadata=frame_metadata,
    )
