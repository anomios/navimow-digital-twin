"""Stable snapshot helpers for bridge consumers such as FHEM."""
from __future__ import annotations

MODULE_NAME = "snapshot"
MODULE_VERSION = "2.0.0"
PROJECT_VERSION = "7.4.0"

from typing import Any


def compact_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Return a flat, stable bridge payload from a nested model snapshot."""
    location = snapshot.get("location") or {}
    motion = snapshot.get("motion") or {}
    geometry = snapshot.get("geometry") or {}
    trail = snapshot.get("trail") or {}
    return {
        "motionState": motion.get("motion", "unknown"),
        "motionStateDetail": snapshot.get("motion_detail", "unknown"),
        "speedMps": round(float(motion.get("speed_mps") or 0.0), 3),
        "accelerationMps2": round(float(motion.get("acceleration_mps2") or 0.0), 3),
        "headingDegrees": None if motion.get("heading_degrees") is None else round(float(motion["heading_degrees"]), 1),
        "headingCardinal": motion.get("heading_cardinal", ""),
        "turnRateDps": round(float(motion.get("turn_rate_dps") or 0.0), 1),
        "moving": 1 if motion.get("moving") else 0,
        "turning": 1 if motion.get("turning") else 0,
        "distanceSession": round(float(motion.get("distance_session_m") or 0.0), 2),
        "locationArea": geometry.get("location_area", "unknown"),
        "currentZoneId": geometry.get("current_zone_id", ""),
        "currentZoneName": geometry.get("current_zone_name", ""),
        "insideBoundary": 1 if geometry.get("inside_boundary") else 0,
        "inTunnel": 1 if geometry.get("in_tunnel") else 0,
        "tunnelId": geometry.get("tunnel_id", ""),
        "dockDistance": None if geometry.get("dock_distance_m") is None else round(float(geometry["dock_distance_m"]), 2),
        "dockBearingDegrees": None if geometry.get("dock_bearing_degrees") is None else round(float(geometry["dock_bearing_degrees"]), 1),
        "dockBearingCardinal": geometry.get("dock_bearing_cardinal", ""),
        "nearDock": 1 if geometry.get("near_dock") else 0,
        "postureX": location.get("x"),
        "postureY": location.get("y"),
        "postureTheta": location.get("theta"),
        "modelLastUpdate": snapshot.get("updated_at"),
        "trailPointCount": trail.get("point_count", 0),
        "trailDistance": trail.get("distance_m", 0.0),
    }
