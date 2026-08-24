"""
##############################################################################
#
# Navimow Digital Twin
#
# Module      : navimow_bridge.py
# Version     : 1.0.0
# Project     : 1.0.0
# Created     : 2026-07-30
# Last Change : 2026-08-23
#
# Copyright (C) 2026 Klaus Resch aka curiosus/anomios
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Description :
# Private-cloud bridge between the Navimow Digital Twin library and FHEM.
#
# Public API  :
# main()
#
# Change History
#
# 1.0.0   2026-08-24
#   First public release, based on internal development version 7.8.55.
#
# 7.8.53  2026-08-23
#   Changed:
#     - MQTT client now uses Paho Callback API VERSION2
#     - Updated connect/subscribe/disconnect callback signatures for Paho 2.x
#     - Removes the "Callback API version 1 is deprecated" warning
#
# 7.8.25  2026-08-16
#   Fixed:
#     - Weekly schedule normalization now merges legacy `plan` and `plan_v2`
#       per day instead of relying on only one representation
#     - Uses `plan_v2` when it contains real periods, otherwise falls back to
#       legacy `plan`
#     - Preserves partition/zone ids from `plan_v2`
#     - Prevents active schedules from appearing empty when only one API
#       representation carries the actual time periods
#
#
# 7.8.24  2026-08-16
#   Consolidated:
#     - Header/project/runtime versions aligned after schedule-reading work
#     - Schedule read path kept unchanged (already proven in 7.8.23)
#     - FHEMWEB schedule presentation is delivered by navimow_live.js 1.6.0
#
# --------------
#
# 7.8.13  2026-08-13
# MQTT hardening:
# - Drops out-of-order state messages with older timestamps
# - Treats Navimow's raw 'isIdel' as a transient/non-authoritative state
# - Keeps the last meaningful mowing/paused/returning/docked state across isIdel
# - Exposes the ignored raw state/timestamp diagnostically without changing FHEM state
#
# 7.8.12  2026-08-13
# MQTT:
# - Normalizes real Navimow MQTT states:
#     isRunning -> mowing
#     isPaused  -> paused
#     isDocking -> returning
#     isDocked  -> docked
# - Emits the normalized state through the existing type=status path
# - Exposes mqttState/mqttStateRaw in navimow_state.js
# - Raw MQTT logging is no longer emitted as an unknown bridge message
#
# 7.8.11  2026-08-13
# MQTT:
# - Uses broker/WebSocket credentials obtained by the FHEM module
# - Direct Paho WebSocket connection; private cloud remains independent
# - Emits raw downlink messages for protocol discovery
#
# 7.8.10  2026-08-13
# Diagnostic:
# - Emits every raw MQTT message as mqttRaw before SDK decoding
# - Keeps original SDK on_message processing intact
# - Explicitly subscribes the attributes topic for comparison
#
# 7.8.9   2026-08-13
# Added:
# - Optional parallel MQTT status channel via installed mower_sdk
# - Real-time states: mowing, paused, returning, docked
# - MQTT failure isolation; private cloud remains operational
#
# 7.8.7   2026-08-11
# Added:
# - Explicit mowZones mode: resume or restart
# - Uses the proven MOW_SETUP_CONTINUE / MOW_SETUP_RESTART constants
# - A successful restart command clears the local trail immediately
# - A successful resume command preserves the existing trail
#
# 7.8.6   2026-08-11
# Changed:
# - Trail persistence now distinguishes resume from explicit progress reset
# - Existing trail is retained while mowing progress continues
# - Trail is cleared only on strong reset evidence (path change or simultaneous
#   backward reset of mowingPercentage and subtotalArea)
# Added:
# - Persisted trail progress metadata and trail reset diagnostics
#
# 7.8.5   2026-08-11
# Added:
# - Runtime JSON command channel after initial stdin configuration
# - Zone-specific private mowZones command
# - Zone id/name metadata in mapDetail events
#
# 7.8.4   2026-08-11
#   Diagnostic:
#     - Adds slow read-only today_plan() polling
#     - Stores raw today-plan response in navimow_today_plan.json
#     - Exposes raw plan/task fields in navimow_state.js
#     - No semantic mapping to "single mow" / schedule yet
#
# 7.8.3   2026-08-11
#   Added:
#     - Slow read-only index2 poll for battery/SOC data
#     - Slow read-only set-list poll for battery operating limits
#     - Live-state fields for battery and mowing-area statistics
#     - Derived batteryWindowPercent within return/charge limits
#   Removed:
#     - Temporary 7.8.2 map-list diagnostic request/dump
#
# 7.8.2   2026-08-09
#   Diagnostic:
#     - Calls private API map_list() once after session startup
#     - Stores raw response in navimow_map_list.json
#     - Emits non-fatal mapList diagnostic state
#
# 7.8.1   2026-08-08
#   Added:
#     - Mower-free base SVG for cross-origin SmartVisu display
#     - Cross-origin JavaScript/JSONP live state feed
#     - Screen-space mower state for delayed browser interpolation
#
# 7.7.9   2026-08-08
#   Added:
#     - Live pipeline timing diagnostics
#     - Position-change interval measurement
#     - Rotating JSONL diagnostics file
#
# 7.7.8   2026-08-08
#   Fixed:
#     - Added missing _resolve_mower_icon() helper
#     - Custom mower icon can now be embedded as a data URI
#
# 7.7.1   2026-08-04
#   Added:
#     - Live SVG from the real model snapshot and map geometry
#     - Renderer API and SVG Renderer integration
#     - Configurable live SVG output path and dimensions
#
# 7.6.2b  2026-08-03
#   Added:
#     - EventTimelineEngine integration
#     - Event timeline size and sequence in modelState
#     - Atomic export of recent semantic events
#     - EventTimeline module version reporting
#
# 7.6.1   2026-08-03
#   Fixed:
#     - Added missing standard-library import `time`
#
# 7.6.0   2026-08-03
#   Added:
#     - Raw timeline export for `get timeline`
#
##############################################################################

Navimow private-cloud bridge for FHEM with Digital Twin model.

Input:
    Exactly one JSON object on stdin.

Required fields:
    deviceId

Output:
    One JSON object per line on stdout.

All diagnostic logging is written to stderr so that stdout remains a
machine-readable communication channel for FHEM.
"""

from __future__ import annotations


from __future__ import annotations

BRIDGE_VERSION = "1.0.0"
PROJECT_VERSION = "1.0.0"

import argparse
import asyncio
import base64
import json
import math
import mimetypes
import logging
import os
import sys
import traceback
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import aiohttp
import paho.mqtt.client as paho_mqtt
from mower_sdk import MowerClient
from mower_sdk.models import DeviceStatus



def emit(message_type: str, **fields: Any) -> None:
    """Write one compact JSON message to stdout."""

    message = {
        "type": message_type,
        **fields,
    }

    print(
        json.dumps(
            message,
            ensure_ascii=False,
            separators=(",", ":"),
        ),
        flush=True,
    )


def log(message: str) -> None:
    """Write a diagnostic message to stderr."""

    print(message, file=sys.stderr, flush=True)


def read_configuration() -> dict[str, Any]:
    """Read and validate the JSON configuration from stdin."""

    line = sys.stdin.readline()

    if not line:
        raise ValueError("No configuration received on stdin")

    try:
        configuration = json.loads(line)
    except json.JSONDecodeError as error:
        raise ValueError(
            f"Ungültige Konfigurations-JSON: {error.msg}"
        ) from error

    if not isinstance(configuration, dict):
        raise ValueError("Configuration must be a JSON object")

    required_fields = {
        "deviceId": configuration.get("deviceId"),
    }

    missing_fields = [
        field_name
        for field_name, field_value in required_fields.items()
        if not isinstance(field_value, str) or not field_value.strip()
    ]

    if missing_fields:
        raise ValueError(
            "Fehlende Konfigurationsfelder: "
            + ", ".join(missing_fields)
        )

    return configuration


def redact(text: str, secrets: list[str]) -> str:
    """Remove known secrets from an error message."""

    result = text

    for secret in secrets:
        if secret:
            result = result.replace(secret, "<redacted>")

    return result


def _normalise_location(data: dict[str, Any]) -> dict[str, Any]:
    """Convert private-cloud field names to stable bridge field names."""

    mapping = {
        "latitude": "latitude",
        "longitude": "longitude",
        "last_latitude": "lastLatitude",
        "last_longitude": "lastLongitude",
        "posture_x": "postureX",
        "posture_y": "postureY",
        "posture_theta": "postureTheta",
        "last_posture_x": "lastPostureX",
        "last_posture_y": "lastPostureY",
        "last_posture_theta": "lastPostureTheta",
        "map_id": "mapId",
        "map_base_id": "mapBaseId",
        "map_edit_time": "mapEditTime",
        "map_work_position": "mapWorkPosition",
        "mowing_percentage": "mowingPercentage",
        "mowing_week_area": "mowingWeekArea",
        "subtotal_area": "subtotalArea",
        "path_id": "pathId",
        "report_time": "reportTime",
        "rtk": "rtk",
    }

    result: dict[str, Any] = {}
    for source, target in mapping.items():
        if source in data and data[source] is not None:
            result[target] = data[source]

    return result


def _write_json_atomic(path: Path, data: Any) -> int:
    """Write JSON atomically and return the resulting file size."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    encoded = json.dumps(
        data,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    temporary.write_bytes(encoded)
    os.chmod(temporary, 0o600)
    temporary.replace(path)
    return len(encoded)



def _xy_points(value: Any) -> list[list[float]]:
    """Return valid [x, y] points from a Navimow point array."""
    result: list[list[float]] = []
    if not isinstance(value, list):
        return result
    for point in value:
        if not isinstance(point, (list, tuple)) or len(point) < 2:
            continue
        try:
            result.append([float(point[0]), float(point[1])])
        except (TypeError, ValueError):
            continue
    return result


def _extract_map_geometry(response: Any) -> dict[str, Any]:
    """Normalise the private map-detail response into stable geometry JSON."""
    if not isinstance(response, dict):
        raise ValueError("map-detail response is not an object")
    raw = response.get("map_detail")
    if isinstance(raw, str):
        detail = json.loads(raw)
    elif isinstance(raw, dict):
        detail = raw
    else:
        raise ValueError("map-detail contains no map_detail object/string")
    if not isinstance(detail, dict):
        raise ValueError("decoded map_detail is not an object")

    zones: list[dict[str, Any]] = []
    docks: list[dict[str, Any]] = []
    all_points: list[list[float]] = []

    for sub_map in detail.get("sub_maps") or []:
        if not isinstance(sub_map, dict):
            continue
        zone = {
            "id": sub_map.get("id"),
            "name": sub_map.get("name") or f"Zone {sub_map.get('id', '')}",
            "area": sub_map.get("area"),
            "boundaries": [],
        }
        for element in sub_map.get("elements") or []:
            if not isinstance(element, dict):
                continue
            kind = str(element.get("type") or "")
            if kind == "BOUNDARY":
                points = _xy_points(element.get("points"))
                if points:
                    zone["boundaries"].append({
                        "id": element.get("id"),
                        "name": element.get("name") or zone["name"],
                        "boundaryType": element.get("boundary_type"),
                        "area": element.get("area"),
                        "points": points,
                    })
                    all_points.extend(points)
            elif kind == "CHARGING_PILE":
                position = _xy_points([element.get("position")])
                nav_position = _xy_points([element.get("nav_pos")])
                dock = {
                    "id": element.get("id"),
                    "name": element.get("name") or "pile",
                    "position": position[0] if position else None,
                    "navPosition": nav_position[0] if nav_position else None,
                    "direction": element.get("direction"),
                    "width": element.get("width"),
                    "length": element.get("length"),
                }
                docks.append(dock)
                if dock["position"]:
                    all_points.append(dock["position"])
        if zone["boundaries"]:
            zones.append(zone)

    obstacles: list[dict[str, Any]] = []
    for item in detail.get("obstacles") or []:
        if not isinstance(item, dict):
            continue
        points = _xy_points(item.get("points"))
        if not points:
            continue
        obstacles.append({
            "id": item.get("id"),
            "name": item.get("name") or f"Obstacle {item.get('id', '')}",
            "area": item.get("area"),
            "points": points,
        })
        all_points.extend(points)

    tunnels: list[dict[str, Any]] = []
    for item in detail.get("tunnels") or []:
        if not isinstance(item, dict):
            continue
        points = _xy_points(item.get("points"))
        if not points:
            continue
        tunnels.append({
            "id": item.get("id"),
            "name": item.get("name") or "tunnel",
            "connection": item.get("connection"),
            "points": points,
        })
        all_points.extend(points)

    vision_off: list[dict[str, Any]] = []
    for item in detail.get("vision_off_areas") or []:
        if not isinstance(item, dict):
            continue
        points = _xy_points(item.get("points"))
        if not points:
            continue
        vision_off.append({
            "id": item.get("id"),
            "name": item.get("name") or "vision_off_area",
            "points": points,
        })
        all_points.extend(points)

    if not all_points:
        raise ValueError("map contains no drawable coordinates")
    xs = [point[0] for point in all_points]
    ys = [point[1] for point in all_points]
    padding = 0.75
    bounds = {
        "minX": min(xs) - padding,
        "maxX": max(xs) + padding,
        "minY": min(ys) - padding,
        "maxY": max(ys) + padding,
    }
    bounds["width"] = bounds["maxX"] - bounds["minX"]
    bounds["height"] = bounds["maxY"] - bounds["minY"]

    return {
        "mapId": str(response.get("map_id") or detail.get("id") or ""),
        "mapBaseId": str(response.get("map_base_id") or ""),
        "name": response.get("map_name") or detail.get("name") or "map",
        "area": detail.get("area"),
        "northOffset": detail.get("map_north_offset"),
        "originGps": detail.get("origin_gps"),
        "centerGps": detail.get("center_gps"),
        "bounds": bounds,
        "zones": zones,
        "obstacles": obstacles,
        "tunnels": tunnels,
        "visionOffAreas": vision_off,
        "docks": docks,
    }


def _svg_points(points: list[list[float]]) -> str:
    return " ".join(f"{x:.4f},{-y:.4f}" for x, y in points)


def _trail_distance(points: list[list[float]]) -> float:
    """Return the accumulated Euclidean trail distance in map metres."""
    import math
    total = 0.0
    for previous, current in zip(points, points[1:]):
        total += math.hypot(current[0] - previous[0], current[1] - previous[1])
    return total


def _load_trail(path: Path) -> dict[str, Any]:
    """Load a persisted trail defensively."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {"mapId": "", "pathId": "", "points": []}
    if not isinstance(data, dict):
        return {"mapId": "", "pathId": "", "points": []}
    points = _xy_points(data.get("points"))
    return {
        "mapId": str(data.get("mapId") or ""),
        "pathId": str(data.get("pathId") or ""),
        "points": points,
    }



def _number_or_none(value: Any) -> float | None:
    """Return a finite float or None."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def _progress_reset_detected(
    previous_percentage: Any,
    current_percentage: Any,
    previous_area: Any,
    current_area: Any,
) -> bool:
    """Conservatively identify Navimow's 'delete progress/start over' case.

    A percentage drop alone is not sufficient because task/zone transitions can
    legitimately change percentage.  We require both progress measures to move
    substantially backwards at the same time.
    """
    old_pct = _number_or_none(previous_percentage)
    new_pct = _number_or_none(current_percentage)
    old_area = _number_or_none(previous_area)
    new_area = _number_or_none(current_area)

    if None in (old_pct, new_pct, old_area, new_area):
        return False

    pct_drop = old_pct - new_pct
    area_drop = old_area - new_area

    # Strong/conservative signal: at least 10 percentage points backwards and
    # at least 1 m² / 20 percent of the previous subtotal backwards.
    required_area_drop = max(1.0, old_area * 0.20)

    return (
        old_pct >= 10.0
        and pct_drop >= 10.0
        and old_area >= 1.0
        and area_drop >= required_area_drop
    )

def _render_map_svg(
    geometry: dict[str, Any],
    location: dict[str, Any] | None,
    trail: list[list[float]] | None = None,
) -> str:
    """Render a self-contained SVG using map metres as viewBox units."""
    import math
    bounds = geometry["bounds"]
    min_x = float(bounds["minX"]); max_y = float(bounds["maxY"])
    width = float(bounds["width"]); height = float(bounds["height"])
    view_y = -max_y
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{min_x:.4f} {view_y:.4f} {width:.4f} {height:.4f}" preserveAspectRatio="xMidYMid meet">',
        '<style>.zone{fill:#b7dca8;stroke:#315b2d;stroke-width:.08}.obstacle{fill:#d98989;stroke:#7b2525;stroke-width:.06}.vision{fill:#f5d67a;fill-opacity:.30;stroke:#b08a16;stroke-width:.04;stroke-dasharray:.18 .12}.tunnel{fill:none;stroke:#587bb8;stroke-width:.12;stroke-dasharray:.25 .15}.dock{fill:#555;stroke:#111;stroke-width:.04}.trail{fill:none;stroke:#1976d2;stroke-width:.12;stroke-linecap:round;stroke-linejoin:round;opacity:.80}.mower{fill:#1e88e5;stroke:#0b3d68;stroke-width:.05}</style>',
        '<rect x="-1000" y="-1000" width="2000" height="2000" fill="#f7f7f2"/>',
    ]
    for zone in geometry.get("zones", []):
        for boundary in zone.get("boundaries", []):
            parts.append(f'<polygon class="zone" points="{_svg_points(boundary["points"])}"><title>{zone.get("name", "Zone")}</title></polygon>')
    for obstacle in geometry.get("obstacles", []):
        parts.append(f'<polygon class="obstacle" points="{_svg_points(obstacle["points"])}"><title>{obstacle.get("name", "Obstacle")}</title></polygon>')
    for area in geometry.get("visionOffAreas", []):
        parts.append(f'<polygon class="vision" points="{_svg_points(area["points"])}"/>')
    for tunnel in geometry.get("tunnels", []):
        parts.append(f'<polyline class="tunnel" points="{_svg_points(tunnel["points"])}"/>')
    for dock in geometry.get("docks", []):
        pos = dock.get("position")
        if pos:
            x, y = float(pos[0]), -float(pos[1])
            parts.append(f'<rect class="dock" x="{x-0.22:.4f}" y="{y-0.12:.4f}" width=".44" height=".24" rx=".05"><title>Ladestation</title></rect>')
    if trail and len(trail) >= 2:
        parts.append(
            f'<polyline class="trail" points="{_svg_points(trail)}">'
            '<title>Aktuelle Fahrspur</title></polyline>'
        )
    if location:
        try:
            x = float(location.get("postureX")); y = -float(location.get("postureY"))
            theta = float(location.get("postureTheta", 0.0))
            angle = -math.degrees(theta)
            parts.append(f'<g transform="translate({x:.4f} {y:.4f}) rotate({angle:.3f})"><path class="mower" d="M .32 0 L -.22 -.22 L -.12 0 L -.22 .22 Z"><title>Navimow</title></path></g>')
        except (TypeError, ValueError):
            pass
    parts.append('</svg>')
    return "".join(parts)


def _write_text_atomic(path: Path, text: str, mode: int = 0o644) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    encoded = text.encode("utf-8")
    temporary.write_bytes(encoded)
    os.chmod(temporary, mode)
    temporary.replace(path)
    return len(encoded)

def _map_detail_summary(data: Any) -> dict[str, Any]:
    """Return log-safe structural metadata for an unparsed map response."""

    summary: dict[str, Any] = {
        "responseType": type(data).__name__,
    }

    if isinstance(data, dict):
        summary["topLevelKeys"] = sorted(str(key) for key in data.keys())
        map_detail = data.get("map_detail")
        if isinstance(map_detail, str):
            summary["mapDetailStringBytes"] = len(map_detail.encode("utf-8"))
            try:
                decoded = json.loads(map_detail)
            except (TypeError, ValueError):
                pass
            else:
                summary["mapDetailDecodedType"] = type(decoded).__name__
                if isinstance(decoded, dict):
                    summary["mapDetailKeys"] = sorted(
                        str(key) for key in decoded.keys()
                    )
                elif isinstance(decoded, list):
                    summary["mapDetailItems"] = len(decoded)
    elif isinstance(data, list):
        summary["topLevelItems"] = len(data)

    return summary


def _append_jsonl_bounded(
    path: Path,
    payload: dict[str, Any],
    *,
    max_bytes: int = 2_000_000,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.stat().st_size >= max_bytes:
        rotated = path.with_suffix(path.suffix + ".1")
        try:
            rotated.unlink(missing_ok=True)
        except Exception:
            pass
        path.replace(rotated)

    with path.open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
            + "\n"
        )


def _load_mowing_session(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except FileNotFoundError:
        return None
    except Exception:
        return None


def _append_mowing_history(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")




def _read_mowing_history(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    item = json.loads(line)
                except Exception:
                    continue
                if isinstance(item, dict):
                    records.append(item)
    except FileNotFoundError:
        pass
    except Exception:
        pass
    return records


def _mowing_history_statistics(
    path: Path,
    now: datetime | None = None,
) -> dict[str, Any]:
    now = now or datetime.now().astimezone()
    records = _read_mowing_history(path)

    result: dict[str, Any] = {
        "todayRuns": 0,
        "todayMowingSeconds": 0.0,
        "todayDurationSeconds": 0.0,
        "todayDistanceM": 0.0,
        "todayAreaM2": 0.0,
        "weekRuns": 0,
        "weekMowingSeconds": 0.0,
        "weekDurationSeconds": 0.0,
        "weekDistanceM": 0.0,
        "weekAreaM2": 0.0,
        "monthRuns": 0,
        "monthMowingSeconds": 0.0,
        "monthDurationSeconds": 0.0,
        "monthDistanceM": 0.0,
        "monthAreaM2": 0.0,
        "last": None,
    }

    week_key = now.isocalendar()[:2]
    month_key = (now.year, now.month)
    today_key = now.date()

    def add(prefix: str, item: dict[str, Any]) -> None:
        result[prefix + "Runs"] += 1
        for src, suffix in (
            ("mowingSeconds", "MowingSeconds"),
            ("durationSeconds", "DurationSeconds"),
            ("distanceM", "DistanceM"),
            ("areaM2", "AreaM2"),
        ):
            try:
                result[prefix + suffix] += float(item.get(src) or 0.0)
            except (TypeError, ValueError):
                pass

    valid: list[tuple[float, dict[str, Any]]] = []
    for item in records:
        try:
            ended_at = float(item.get("endedAt"))
        except (TypeError, ValueError):
            continue
        ended_dt = datetime.fromtimestamp(ended_at, tz=now.tzinfo)
        valid.append((ended_at, item))

        if ended_dt.date() == today_key:
            add("today", item)
        if ended_dt.isocalendar()[:2] == week_key:
            add("week", item)
        if (ended_dt.year, ended_dt.month) == month_key:
            add("month", item)

    if valid:
        valid.sort(key=lambda pair: pair[0])
        result["last"] = dict(valid[-1][1])

    for prefix in ("today", "week", "month"):
        result[prefix + "MowingSeconds"] = round(result[prefix + "MowingSeconds"], 1)
        result[prefix + "DurationSeconds"] = round(result[prefix + "DurationSeconds"], 1)
        result[prefix + "DistanceM"] = round(result[prefix + "DistanceM"], 2)
        result[prefix + "AreaM2"] = round(result[prefix + "AreaM2"], 2)

    return result





def _clean_segmented_trail(
    points: list[list[float]],
    *,
    outlier_leg_m: float = 1.5,
    outlier_return_m: float = 1.0,
    segment_jump_m: float = 4.0,
) -> tuple[list[list[float]], list[int], int]:
    clean = []
    removed = 0
    src = []

    for raw in points or []:
        if not isinstance(raw, (list, tuple)) or len(raw) < 2:
            continue
        try:
            src.append([float(raw[0]), float(raw[1])])
        except (TypeError, ValueError):
            continue

    i = 0
    while i < len(src):
        if 0 < i < len(src) - 1:
            a = src[i - 1]
            b = src[i]
            c = src[i + 1]
            ab = math.hypot(b[0] - a[0], b[1] - a[1])
            bc = math.hypot(c[0] - b[0], c[1] - b[1])
            ac = math.hypot(c[0] - a[0], c[1] - a[1])

            global_outlier = ab > outlier_leg_m and bc > outlier_leg_m and ac < outlier_return_m
            dock_outlier = (
                abs(a[0]) < 5.0 and abs(a[1]) < 5.0
                and abs(b[0]) < 5.0 and abs(b[1]) < 5.0
                and abs(c[0]) < 5.0 and abs(c[1]) < 5.0
                and ab > 1.2 and bc > 1.2 and ac < 0.4
            )
            if global_outlier or dock_outlier:
                removed += 1
                i += 1
                continue

        clean.append(src[i])
        i += 1

    breaks = []
    for idx in range(1, len(clean)):
        distance = math.hypot(clean[idx][0] - clean[idx - 1][0], clean[idx][1] - clean[idx - 1][1])
        previous_near_zero = math.hypot(clean[idx - 1][0], clean[idx - 1][1]) <= 0.15
        current_near_zero = math.hypot(clean[idx][0], clean[idx][1]) <= 0.15
        dock_zero_jump = distance > 1.5 and (previous_near_zero or current_near_zero)
        if distance > segment_jump_m or dock_zero_jump:
            breaks.append(idx)

    return clean, breaks, removed

def _trail_polyline_distance(
    point: list[float] | tuple[float, float],
    line: list | tuple,
) -> float | None:
    """Shortest distance in metres from point to a polyline."""
    if not isinstance(line, (list, tuple)) or len(line) < 2:
        return None

    try:
        px=float(point[0])
        py=float(point[1])
    except (TypeError, ValueError, IndexError):
        return None

    best=None

    for idx in range(1,len(line)):
        try:
            ax=float(line[idx-1][0])
            ay=float(line[idx-1][1])
            bx=float(line[idx][0])
            by=float(line[idx][1])
        except (TypeError, ValueError, IndexError):
            continue

        dx=bx-ax
        dy=by-ay

        if dx == 0.0 and dy == 0.0:
            distance=math.hypot(px-ax,py-ay)
        else:
            t=((px-ax)*dx+(py-ay)*dy)/(dx*dx+dy*dy)
            t=max(0.0,min(1.0,t))

            qx=ax+t*dx
            qy=ay+t*dy

            distance=math.hypot(px-qx,py-qy)

        if best is None or distance < best:
            best=distance

    return best


def _trail_distance_segmented(points: list[list[float]], breaks: list[int] | None = None) -> float:
    if len(points) < 2:
        return 0.0
    break_set = {int(x) for x in (breaks or [])}
    total = 0.0
    for idx in range(1, len(points)):
        if idx in break_set:
            continue
        try:
            total += math.hypot(
                float(points[idx][0]) - float(points[idx-1][0]),
                float(points[idx][1]) - float(points[idx-1][1]),
            )
        except (TypeError, ValueError, IndexError):
            pass
    return total


def _resolve_mower_icon(value: Any) -> str:
    """Resolve a configured mower icon to an embeddable data URI.

    Supported values:
    - empty string: use the built-in mower symbol
    - data URI: passed through unchanged
    - /fhem/... URL: mapped to /opt/fhem/www/...
    - absolute local file path: read directly
    """
    text = str(value or "").strip()
    if not text:
        return ""

    if text.startswith("data:"):
        return text

    candidate = text
    if text.startswith("/fhem/"):
        candidate = "/opt/fhem/www/" + text[len("/fhem/"):]

    path = Path(candidate)
    if not path.is_file():
        return ""

    mime, _ = mimetypes.guess_type(path.name)
    mime = mime or "application/octet-stream"

    payload = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{payload}"



def _normalise_week_schedule(settings_data: dict[str, Any]) -> dict[str, Any]:
    day_names = {
        1: "Sonntag", 2: "Montag", 3: "Dienstag", 4: "Mittwoch",
        5: "Donnerstag", 6: "Freitag", 7: "Samstag",
    }
    short_names = {
        1: "So", 2: "Mo", 3: "Di", 4: "Mi",
        5: "Do", 6: "Fr", 7: "Sa",
    }

    enabled = str(settings_data.get("startPlan", "0")).strip() == "1"

    raw_plan = settings_data.get("plan")
    if not isinstance(raw_plan, list):
        raw_plan = []

    raw_plan_v2 = settings_data.get("plan_v2")
    if not isinstance(raw_plan_v2, list):
        raw_plan_v2 = []

    by_day_v1: dict[int, dict[str, Any]] = {}
    by_day_v2: dict[int, dict[str, Any]] = {}

    for item in raw_plan:
        if not isinstance(item, dict):
            continue
        try:
            day = int(item.get("day"))
        except (TypeError, ValueError):
            continue
        by_day_v1[day] = item

    for item in raw_plan_v2:
        if not isinstance(item, dict):
            continue
        try:
            day = int(item.get("day"))
        except (TypeError, ValueError):
            continue
        by_day_v2[day] = item

    days = []
    summary_parts = []

    for day in range(1, 8):
        v1 = by_day_v1.get(day) or {}
        v2 = by_day_v2.get(day) or {}

        try:
            enabled_v1 = bool(int(v1.get("open") or 0))
        except (TypeError, ValueError):
            enabled_v1 = False

        try:
            enabled_v2 = bool(int(v2.get("open") or 0))
        except (TypeError, ValueError):
            enabled_v2 = False

        periods_v1 = []
        for raw_period in v1.get("period") or []:
            if not isinstance(raw_period, (list, tuple)) or len(raw_period) < 2:
                continue
            try:
                start_slot = int(raw_period[0])
                end_slot = int(raw_period[1])
            except (TypeError, ValueError):
                continue

            start_minutes = start_slot * 15
            end_minutes = end_slot * 15
            periods_v1.append({
                "startSlot": start_slot,
                "endSlot": end_slot,
                "start": f"{start_minutes // 60:02d}:{start_minutes % 60:02d}",
                "end": f"{end_minutes // 60:02d}:{end_minutes % 60:02d}",
                "partitionIds": [],
                "source": "plan",
            })

        periods_v2 = []
        for raw_period in v2.get("period") or []:
            if not isinstance(raw_period, dict):
                continue
            try:
                start_slot = int(raw_period.get("start_time"))
                end_slot = int(raw_period.get("end_time"))
            except (TypeError, ValueError):
                continue

            partition_ids = []
            for value in raw_period.get("partition_ids") or []:
                try:
                    partition_ids.append(int(value))
                except (TypeError, ValueError):
                    continue

            start_minutes = start_slot * 15
            end_minutes = end_slot * 15
            periods_v2.append({
                "startSlot": start_slot,
                "endSlot": end_slot,
                "start": f"{start_minutes // 60:02d}:{start_minutes % 60:02d}",
                "end": f"{end_minutes // 60:02d}:{end_minutes % 60:02d}",
                "partitionIds": partition_ids,
                "source": "plan_v2",
            })

        if periods_v2:
            periods = periods_v2
            day_enabled = enabled_v2
            source = "plan_v2"
        elif periods_v1:
            periods = periods_v1
            day_enabled = enabled_v1
            source = "plan"
        else:
            periods = []
            day_enabled = enabled_v2 or enabled_v1
            source = "plan_v2" if v2 else ("plan" if v1 else "")

        for period in periods:
            if day_enabled:
                summary_parts.append(
                    f'{short_names.get(day, str(day))} '
                    f'{period["start"]}-{period["end"]}'
                )

        days.append({
            "day": day,
            "name": day_names.get(day, str(day)),
            "enabled": day_enabled,
            "periods": periods,
            "source": source,
        })

    return {
        "enabled": enabled,
        "days": days,
        "summary": ", ".join(summary_parts) if summary_parts else "aus",
    }



def _schedule_runtime_fields(schedule_state: dict[str, Any]) -> dict[str, Any]:
    enabled = bool(schedule_state.get("enabled"))
    days = schedule_state.get("days") or []

    result: dict[str, Any] = {
        "today": "aus",
        "next": "",
        "nextDate": "",
        "nextDay": "",
        "nextStart": "",
        "nextEnd": "",
        "nextInMinutes": None,
    }

    if not enabled or not isinstance(days, list):
        return result

    now = datetime.now().astimezone()
    nav_today = ((now.weekday() + 1) % 7) + 1

    by_day: dict[int, dict[str, Any]] = {}
    for item in days:
        if not isinstance(item, dict):
            continue
        try:
            day_no = int(item.get("day"))
        except (TypeError, ValueError):
            continue
        by_day[day_no] = item

    today_item = by_day.get(nav_today)
    if today_item and bool(today_item.get("enabled")):
        today_periods: list[str] = []
        for period in today_item.get("periods") or []:
            if not isinstance(period, dict):
                continue
            start_text = str(period.get("start") or "")
            end_text = str(period.get("end") or "")
            if start_text and end_text:
                today_periods.append(f"{start_text}-{end_text}")
        if today_periods:
            result["today"] = ", ".join(today_periods)

    candidates: list[tuple[datetime, datetime, str]] = []

    for day_offset in range(0, 8):
        candidate_date = now.date() + timedelta(days=day_offset)
        candidate_nav_day = ((candidate_date.weekday() + 1) % 7) + 1
        item = by_day.get(candidate_nav_day)
        if not item or not bool(item.get("enabled")):
            continue

        day_name = str(item.get("name") or candidate_nav_day)

        for period in item.get("periods") or []:
            if not isinstance(period, dict):
                continue
            start_text = str(period.get("start") or "")
            end_text = str(period.get("end") or "")
            if not start_text or not end_text:
                continue

            try:
                start_hour, start_minute = [int(x) for x in start_text.split(":", 1)]
                end_hour, end_minute = [int(x) for x in end_text.split(":", 1)]
            except (TypeError, ValueError):
                continue

            start_dt = datetime(
                candidate_date.year, candidate_date.month, candidate_date.day,
                start_hour, start_minute, tzinfo=now.tzinfo,
            )
            end_dt = datetime(
                candidate_date.year, candidate_date.month, candidate_date.day,
                end_hour, end_minute, tzinfo=now.tzinfo,
            )
            if end_dt <= start_dt:
                end_dt += timedelta(days=1)
            if start_dt <= now:
                continue

            candidates.append((start_dt, end_dt, day_name))

    if not candidates:
        return result

    start_dt, end_dt, day_name = min(candidates, key=lambda item: item[0])
    result.update({
        "next": f"{day_name} {start_dt:%d.%m.%Y} {start_dt:%H:%M}-{end_dt:%H:%M}",
        "nextDate": start_dt.strftime("%Y-%m-%d"),
        "nextDay": day_name,
        "nextStart": start_dt.strftime("%H:%M"),
        "nextEnd": end_dt.strftime("%H:%M"),
        "nextInMinutes": max(0, int((start_dt - now).total_seconds() // 60)),
    })
    return result


def _today_plan_runtime_fields(plan_state: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {
        "available": False,
        "today": "aus",
        "next": "",
        "nextDate": "",
        "nextDay": "",
        "nextStart": "",
        "nextEnd": "",
        "nextInMinutes": None,
    }

    if not isinstance(plan_state, dict):
        return result

    try:
        day_no = int(plan_state.get("weekDay"))
        start_slot = int(plan_state.get("c_plan_s_time"))
        end_slot = int(plan_state.get("c_plan_e_time"))
    except (TypeError, ValueError):
        return result

    if start_slot <= 0 and end_slot <= 0:
        return result
    if not (1 <= day_no <= 7):
        return result

    now = datetime.now().astimezone()
    nav_today = ((now.weekday() + 1) % 7) + 1
    if day_no != nav_today:
        return result

    start_minutes = start_slot * 15
    end_minutes = end_slot * 15
    start_hour, start_minute = divmod(start_minutes, 60)
    end_hour, end_minute = divmod(end_minutes, 60)

    try:
        start_dt = datetime(
            now.year, now.month, now.day,
            start_hour, start_minute, tzinfo=now.tzinfo,
        )
        end_dt = datetime(
            now.year, now.month, now.day,
            end_hour, end_minute, tzinfo=now.tzinfo,
        )
    except ValueError:
        return result

    if end_dt <= start_dt:
        end_dt += timedelta(days=1)

    day_names = {
        1: "Sonntag", 2: "Montag", 3: "Dienstag", 4: "Mittwoch",
        5: "Donnerstag", 6: "Freitag", 7: "Samstag",
    }
    day_name = day_names.get(day_no, str(day_no))

    result["available"] = True
    result["today"] = f"{start_dt:%H:%M}-{end_dt:%H:%M}"

    if start_dt > now:
        result.update({
            "next": f"{day_name} {start_dt:%d.%m.%Y} {start_dt:%H:%M}-{end_dt:%H:%M}",
            "nextDate": start_dt.strftime("%Y-%m-%d"),
            "nextDay": day_name,
            "nextStart": start_dt.strftime("%H:%M"),
            "nextEnd": end_dt.strftime("%H:%M"),
            "nextInMinutes": max(0, int((start_dt - now).total_seconds() // 60)),
        })

    return result




async def _private_location_loop(
    configuration: dict[str, Any],
    device_id: str,
    secrets: list[str],
    runtime_state: dict[str, Any],
) -> None:
    """Poll the private API using a persistent, refreshable session file."""

    client_path = str(configuration.get(
        "privateClientPath", "/opt/fhem/navimow-python"
    )).strip()
    if client_path and client_path not in sys.path:
        sys.path.insert(0, client_path)

    session_file = Path(str(configuration.get(
        "privateSessionFile",
        "/opt/fhem/navimow-python/cache/navimow_private_session.json",
    )).strip() or "/opt/fhem/navimow-python/cache/navimow_private_session.json")

    if not session_file.is_file():
        emit(
            "privateCloudState", deviceId=device_id, state="disabled",
            message=f"private session file not found: {session_file}",
        )
        return

    try:
        from navimow_private.session import NavimowSession
        from navimow_private.model import (
            MODULE_VERSION as MODEL_VERSION,
            NavimowModel,
        )
        from navimow_private.geometry import MODULE_VERSION as GEOMETRY_VERSION
        from navimow_private.motion import MODULE_VERSION as MOTION_VERSION
        from navimow_private.snapshot import (
            MODULE_VERSION as SNAPSHOT_VERSION,
            compact_snapshot,
        )
        from navimow_private.events import (
            MODULE_VERSION as EVENTS_VERSION,
            EventEngine,
        )
        from navimow_private.history import (
            MODULE_VERSION as HISTORY_VERSION,
            HistoryEngine,
        )
        from navimow_private.timeline import TimelineEngine
        from navimow_private.event_timeline import EventTimelineEngine
        from navimow_private.renderer_api import build_renderer_frame
        from navimow_private.renderer_svg import RendererStyle, SVGRenderer
        from navimow_private.const import (
            MOW_SETUP_CONTINUE,
            MOW_SETUP_RESTART,
            encode_partition_ids,
        )
        private_session = NavimowSession(session_file, client_path=client_path).load()
        client = private_session.client()
        vehicle = private_session.selected_vehicle()
    except Exception as error:
        safe_message = redact(str(error), secrets)
        emit("error", stage="privateSessionLoad", deviceId=device_id, message=safe_message)
        log("Navimow: Laden der privaten Sitzung fehlgeschlagen:")
        traceback.print_exc(file=sys.stderr)
        return

    vehicle_sn = str(vehicle.get("vehicle_sn") or configuration.get("privateVehicleSn") or device_id)
    try:
        vehicle_type = int(vehicle.get("vehicle_type") or configuration.get("privateVehicleType") or 801)
    except (TypeError, ValueError):
        vehicle_type = 801

    model = NavimowModel()
    event_engine = EventEngine()
    try:
        history_max_entries = max(10, min(10000, int(configuration.get("privateHistoryMaxEntries", 1000))))
    except (TypeError, ValueError):
        history_max_entries = 1000
    history_engine = HistoryEngine(history_max_entries)
    try:
        timeline_max_entries = max(
            100,
            min(
                50000,
                int(configuration.get("privateTimelineMaxEntries", 5000)),
            ),
        )
    except (TypeError, ValueError):
        timeline_max_entries = 5000
    timeline_engine = TimelineEngine(timeline_max_entries)
    timeline_file = Path(str(configuration.get(
        "privateTimelineFile",
        "/opt/fhem/navimow-python/cache/navimow_timeline_recent.json",
    )).strip() or "/opt/fhem/navimow-python/cache/navimow_timeline_recent.json")
    try:
        timeline_export_count = max(
            10,
            min(
                500,
                int(configuration.get("privateTimelineExportCount", 100)),
            ),
        )
    except (TypeError, ValueError):
        timeline_export_count = 100

    try:
        event_timeline_max_entries = max(
            10,
            min(
                10000,
                int(configuration.get("privateEventTimelineMaxEntries", 1000)),
            ),
        )
    except (TypeError, ValueError):
        event_timeline_max_entries = 1000
    event_timeline_engine = EventTimelineEngine(event_timeline_max_entries)

    event_timeline_file = Path(str(configuration.get(
        "privateEventTimelineFile",
        "/opt/fhem/navimow-python/cache/navimow_event_timeline_recent.json",
    )).strip() or "/opt/fhem/navimow-python/cache/navimow_event_timeline_recent.json")

    try:
        event_timeline_export_count = max(
            10,
            min(
                500,
                int(configuration.get("privateEventTimelineExportCount", 100)),
            ),
        )
    except (TypeError, ValueError):
        event_timeline_export_count = 100

    try:
        poll_interval_base = max(
            1.0,
            float(configuration.get("privatePollInterval", 3)),
        )
    except (TypeError, ValueError):
        poll_interval_base = 3.0

    poll_interval_active = 1.0
    poll_interval_returning = 1.0
    poll_interval_paused = 2.0
    poll_interval_transition = 5.0
    poll_interval_docked_charging = 20.0
    poll_interval_docked_parked = 30.0
    fast_poll_window_seconds = 30.0
    try:
        status_poll_interval = max(
            10.0,
            float(configuration.get("privateStatusPollInterval", 60)),
        )
    except (TypeError, ValueError):
        status_poll_interval = 60.0

    try:
        settings_poll_interval = max(
            30.0,
            float(configuration.get("privateSettingsPollInterval", 300)),
        )
    except (TypeError, ValueError):
        settings_poll_interval = 300.0
    try:
        plan_poll_interval = max(
            15.0,
            float(configuration.get("privatePlanPollInterval", 30)),
        )
    except (TypeError, ValueError):
        plan_poll_interval = 30.0

    plan_diagnostic_file = Path(str(configuration.get(
        "privatePlanDiagnosticFile",
        "/opt/fhem/navimow-python/cache/navimow_today_plan.json",
    )).strip() or "/opt/fhem/navimow-python/cache/navimow_today_plan.json")
    diagnostics_enabled = str(
        configuration.get("privateLiveDiagnostics", True)
    ).strip().lower() not in {"0", "false", "no", "off", ""}

    diagnostics_file = Path(str(configuration.get(
        "privateLiveDiagnosticsFile",
        "/opt/fhem/navimow-python/cache/navimow_live_diagnostics.jsonl",
    )).strip() or "/opt/fhem/navimow-python/cache/navimow_live_diagnostics.jsonl")

    map_enabled = str(configuration.get("privateMapEnabled", True)).strip().lower() not in {
        "0", "false", "no", "off", ""
    }
    map_file = Path(str(configuration.get(
        "privateMapFile", "/opt/fhem/navimow-python/cache/navimow_map_detail.json"
    )).strip() or "/opt/fhem/navimow-python/cache/navimow_map_detail.json")

    trail_enabled = str(configuration.get("privateTrailEnabled", True)).strip().lower() not in {
        "0", "false", "no", "off", ""
    }
    try:
        trail_max_points = max(10, min(20000, int(configuration.get("privateTrailMaxPoints", 3000))))
    except (TypeError, ValueError):
        trail_max_points = 3000
    try:
        trail_min_distance = max(0.01, float(configuration.get("privateTrailMinDistance", 0.08)))
    except (TypeError, ValueError):
        trail_min_distance = 0.08
    trail_file = Path(str(configuration.get(
        "privateTrailFile", "/opt/fhem/navimow-python/cache/navimow_mowing_trail.json"
    )).strip() or "/opt/fhem/navimow-python/cache/navimow_mowing_trail.json")

    emit("privateCloudState", deviceId=device_id, state="connecting")
    emit(
        "privateCloudState",
        deviceId=device_id,
        state="connected",
        host=str(private_session.data.get("cloud", {}).get("host") or ""),
        vehicleSn=vehicle_sn,
        vehicleType=vehicle_type,
        shared=1 if vehicle.get("shared") else 0,
        sessionFile=str(session_file),
        emailMasked=str(private_session.data.get("account", {}).get("email_masked") or "***"),
    )

    consecutive_errors = 0
    loaded_map_key: tuple[str, str] | None = None
    next_map_retry = 0.0
    map_geometry: dict[str, Any] | None = None
    geometry_file = map_file.with_name("navimow_map_geometry.json")
    live_svg_file = Path(str(configuration.get(
        "privateLiveSvgFile",
        "/opt/fhem/www/images/navimow/live/navimow.svg",
    )).strip() or "/opt/fhem/www/images/navimow/live/navimow.svg")
    live_base_svg_file = live_svg_file.with_name(
        live_svg_file.stem + "_base.svg"
    )
    live_state_js_file = live_svg_file.with_name(
        live_svg_file.stem + "_state.js"
    )

    try:
        live_svg_width = max(
            320,
            min(3840, int(configuration.get("privateLiveSvgWidth", 900))),
        )
    except (TypeError, ValueError):
        live_svg_width = 900

    try:
        live_svg_height = max(
            240,
            min(2160, int(configuration.get("privateLiveSvgHeight", 650))),
        )
    except (TypeError, ValueError):
        live_svg_height = 650

    try:
        live_zoom = float(configuration.get("privateLiveZoom", 1.0))
    except (TypeError, ValueError):
        live_zoom = 1.0
    live_zoom = max(0.1, min(10.0, live_zoom))

    try:
        live_pan_x = float(configuration.get("privateLivePanX", 0.0))
    except (TypeError, ValueError):
        live_pan_x = 0.0
    try:
        live_pan_y = float(configuration.get("privateLivePanY", 0.0))
    except (TypeError, ValueError):
        live_pan_y = 0.0

    try:
        live_trail_width = float(configuration.get("privateLiveTrailWidth", 1.0))
    except (TypeError, ValueError):
        live_trail_width = 1.0

    try:
        live_heading_offset = float(configuration.get("privateLiveHeadingOffset", 90.0))
    except (TypeError, ValueError):
        live_heading_offset = 90.0

    live_style = RendererStyle(
        background=str(configuration.get("privateLiveBackground", "transparent")),
        zone_fill=str(configuration.get("privateLiveZoneFill", "#dfeee0")),
        zone_stroke=str(configuration.get("privateLiveZoneStroke", "#477a4b")),
        trail_stroke=str(configuration.get("privateLiveTrailStroke", "#2f7d32")),
        trail_width=max(0.25, min(20.0, live_trail_width)),
        mower_fill=str(configuration.get("privateLiveMowerFill", "#70b85a")),
        mower_stroke=str(configuration.get("privateLiveMowerStroke", "#1f4d24")),
        heading_offset_degrees=live_heading_offset,
        mower_icon_href=_resolve_mower_icon(
            configuration.get("privateLiveMowerIcon", "")
        ),
        no_go_fill=str(configuration.get("privateLiveNoGoFill", "#8b8b8b")),
        no_go_stroke=str(configuration.get("privateLiveNoGoStroke", "#3f3f3f")),
        vision_off_fill=str(
            configuration.get("privateLiveVisionOffFill", "#d0b35a")
        ),
        vision_off_stroke=str(
            configuration.get("privateLiveVisionOffStroke", "#8c7426")
        ),
    )

    live_svg_renderer = SVGRenderer(
        width=live_svg_width,
        height=live_svg_height,
        show_labels=True,
        style=live_style,
        zoom=live_zoom,
        pan_x=live_pan_x,
        pan_y=live_pan_y,
    )

    trail_state = _load_trail(trail_file) if trail_enabled else {
        "mapId": "", "pathId": "", "points": []
    }
    trail_points: list[list[float]] = list(trail_state.get("points") or [])
    trail_points, trail_breaks, trail_outliers_removed = _clean_segmented_trail(trail_points)
    trail_map_id = str(trail_state.get("mapId") or "")
    trail_path_id = str(trail_state.get("pathId") or "")
    trail_last_percentage = trail_state.get("mowingPercentage")
    trail_last_subtotal_area = trail_state.get("subtotalArea")
    trail_reset_reason = ""
    trail_closed_at_dock = False

    #
    # Tunnel-Map-Matching:
    #
    # candidate = an einem Tunnelende angekommen
    # active    = tatsächliche Bewegung in den Tunnel bestätigt
    #
    trail_tunnel_candidate = None
    trail_tunnel_active = False
    trail_tunnel_target = None

    mowing_history_file = Path(str(configuration.get(
        "privateMowingHistoryFile",
        "/opt/fhem/navimow-python/data/navimow_mowing_history.jsonl",
    )).strip() or "/opt/fhem/navimow-python/data/navimow_mowing_history.jsonl")
    mowing_session_file = Path(str(configuration.get(
        "privateMowingSessionFile",
        "/opt/fhem/navimow-python/cache/navimow_mowing_session.json",
    )).strip() or "/opt/fhem/navimow-python/cache/navimow_mowing_session.json")
    mowing_session = _load_mowing_session(mowing_session_file)
    previous_history_motion = ""

    previous_position_signature: tuple[float, float, float] | None = None
    previous_position_change_wall: float | None = None
    command_queue = runtime_state.get("commandQueue")

    # Slow-changing data is intentionally decoupled from the fast location
    # poll.  Keep the last successful values when a status/settings request
    # temporarily fails.
    battery_state: dict[str, Any] = {}
    battery_limits: dict[str, Any] = {}
    plan_state: dict[str, Any] = {}
    schedule_state: dict[str, Any] = {
        "enabled": False,
        "days": [],
        "summary": "aus",
    }
    next_status_poll = 0.0
    next_settings_poll = 0.0
    next_plan_poll = 0.0

    fast_poll_until = 0.0
    current_poll_interval = poll_interval_base
    current_poll_mode = "base"

    while True:
        loop_clock = asyncio.get_running_loop()
        iteration_started = loop_clock.time()

        # Process runtime commands here, serially with normal API polling.
        if isinstance(command_queue, asyncio.Queue):
            while True:
                try:
                    bridge_command = command_queue.get_nowait()
                except asyncio.QueueEmpty:
                    break

                command_type = str(bridge_command.get("type") or "").strip()
                request_id = str(bridge_command.get("requestId") or "").strip()

                if command_type == "mowZones":
                    try:
                        zone_ids = [
                            int(value)
                            for value in (bridge_command.get("zoneIds") or [])
                        ]
                        if not zone_ids:
                            raise ValueError("mowZones requires at least one zone id")

                        mode = str(
                            bridge_command.get("mode") or "resume"
                        ).strip().lower()
                        if mode not in {"resume", "restart"}:
                            raise ValueError(
                                "mowZones mode must be resume or restart"
                            )

                        partition_setup = (
                            MOW_SETUP_RESTART
                            if mode == "restart"
                            else MOW_SETUP_CONTINUE
                        )

                        result = await asyncio.to_thread(
                            client.mow_zones,
                            vehicle_sn,
                            encode_partition_ids(zone_ids),
                            partition_setup,
                        )
                        await asyncio.to_thread(
                            private_session.sync_from_client,
                            client,
                        )

                        # Keep our trail semantics exactly aligned with the
                        # user's Navimow choice.  Only an accepted restart
                        # starts a new local trail. Resume keeps it intact.
                        if mode == "restart":
                            trail_points = []
                            trail_path_id = ""
                            trail_last_percentage = None
                            trail_last_subtotal_area = None
                            trail_reset_reason = "commandRestart"
                            await asyncio.to_thread(
                                _write_json_atomic,
                                trail_file,
                                {
                                    "mapId": trail_map_id,
                                    "pathId": "",
                                    "mowingPercentage": None,
                                    "subtotalArea": None,
                                    "points": [],
                                },
                            )

                        fast_poll_until = (
                            loop_clock.time() + fast_poll_window_seconds
                        )
                        runtime_state["privatePollMode"] = "command"
                        runtime_state["privatePollIntervalCurrent"] = poll_interval_active

                        emit(
                            "commandResult",
                            deviceId=device_id,
                            requestId=request_id,
                            command="mowZones",
                            ok=True,
                            zoneIds=zone_ids,
                            mode=mode,
                            partitionSetup=partition_setup,
                            trailReset=1 if mode == "restart" else 0,
                            data=result,
                        )
                    except asyncio.CancelledError:
                        raise
                    except Exception as error:
                        emit(
                            "commandResult",
                            deviceId=device_id,
                            requestId=request_id,
                            command="mowZones",
                            ok=False,
                            message=redact(str(error), secrets),
                        )
                else:
                    emit(
                        "commandResult",
                        deviceId=device_id,
                        requestId=request_id,
                        command=command_type,
                        ok=False,
                        message="unknown runtime command",
                    )

        iteration_started = loop_clock.time()
        iteration_wall = time.time()
        request_started = loop_clock.time()
        try:
            location = await asyncio.to_thread(
                client.location,
                vehicle_sn,
                vehicle_type,
            )
            request_ms = (loop_clock.time() - request_started) * 1000.0
            await asyncio.to_thread(private_session.sync_from_client, client)

            if not isinstance(location, dict):
                raise ValueError("private get-location returned no object")

            normalised_location = _normalise_location(location)

            # Battery/status data changes slowly and does not belong in the
            # 1-3 second live-position request cadence.
            if iteration_started >= next_status_poll:
                next_status_poll = iteration_started + status_poll_interval
                try:
                    index2_data = await asyncio.to_thread(
                        client.index2,
                        vehicle_sn,
                    )
                    await asyncio.to_thread(
                        private_session.sync_from_client,
                        client,
                    )
                    if isinstance(index2_data, dict):
                        battery_state = {
                            "soc": index2_data.get("soc"),
                            "soh": index2_data.get("soh"),
                            "batteryStatus": index2_data.get("batteryStatus"),
                            "chgRemainTimeUser": index2_data.get(
                                "chgRemainTimeUser"
                            ),
                            "networkType": index2_data.get("networkType"),
                            "networkStatus": index2_data.get("network_status"),
                            "networkSignal": index2_data.get("network_signal"),
                            "networkSignal4G": index2_data.get("network_signal_4G"),
                            "networkSignalWifi": index2_data.get("network_signal_wifi"),
                        }
                except asyncio.CancelledError:
                    raise
                except Exception as error:
                    log(
                        "Navimow: index2-Statusabfrage fehlgeschlagen: "
                        + redact(str(error), secrets)
                    )

            # Charging limit and return threshold are user settings and change
            # even less frequently.  They are read only and cached.
            if iteration_started >= next_settings_poll:
                next_settings_poll = iteration_started + settings_poll_interval
                try:
                    settings_data = await asyncio.to_thread(
                        client.set_list,
                        vehicle_sn,
                    )
                    await asyncio.to_thread(
                        private_session.sync_from_client,
                        client,
                    )
                    if isinstance(settings_data, dict):
                        battery_limits = {
                            "chargingLimit": settings_data.get(
                                "chargingLimit"
                            ),
                            "returnBatteryLevel": settings_data.get(
                                "returnBatteryLevel"
                            ),
                        }
                except asyncio.CancelledError:
                    raise
                except Exception as error:
                    log(
                        "Navimow: set-list-Einstellungsabfrage fehlgeschlagen: "
                        + redact(str(error), secrets)
                    )

            # Diagnostic plan/task state.  Keep this deliberately raw until
            # values have been observed in docked, manual-mow and scheduled
            # mowing states.
            if iteration_started >= next_plan_poll:
                next_plan_poll = iteration_started + plan_poll_interval
                try:
                    today_plan_data = await asyncio.to_thread(
                        client.today_plan,
                        vehicle_sn,
                        vehicle_type,
                    )
                    await asyncio.to_thread(
                        private_session.sync_from_client,
                        client,
                    )
                    if isinstance(today_plan_data, dict):
                        plan_state = dict(today_plan_data)
                        await asyncio.to_thread(
                            _write_json_atomic,
                            plan_diagnostic_file,
                            today_plan_data,
                        )
                except asyncio.CancelledError:
                    raise
                except Exception as error:
                    log(
                        "Navimow: today-plan-Diagnoseabfrage fehlgeschlagen: "
                        + redact(str(error), secrets)
                    )

            try:
                position_signature = (
                    float(normalised_location.get("postureX")),
                    float(normalised_location.get("postureY")),
                    float(normalised_location.get("postureTheta") or 0.0),
                )
            except (TypeError, ValueError):
                position_signature = None

            position_changed = (
                position_signature is not None
                and position_signature != previous_position_signature
            )
            position_change_interval_ms = None
            if position_changed:
                if previous_position_change_wall is not None:
                    position_change_interval_ms = (
                        iteration_wall - previous_position_change_wall
                    ) * 1000.0
                previous_position_change_wall = iteration_wall
                previous_position_signature = position_signature

            previous_snapshot = model.snapshot()
            previous_motion_detail = str(
                previous_snapshot.get("motion_detail") or ""
            ).lower()
            previous_geometry = previous_snapshot.get("geometry") or {}
            previous_area = str(
                previous_geometry.get("location_area") or ""
            ).lower()

            map_id_text = str(normalised_location.get("mapId") or "")
            path_id_text = str(normalised_location.get("pathId") or "")
            # Im Private-only-Betrieb steht kein MQTT-Status zur Verfügung.
            # Die Spur wird deshalb anhand realer Bewegung aufgebaut.
            trail_active = False
            trail_reset_reason = ""

            current_percentage = normalised_location.get("mowingPercentage")
            current_subtotal_area = normalised_location.get("subtotalArea")

            # A map change is always a hard boundary.
            if (
                trail_enabled
                and trail_map_id
                and map_id_text
                and trail_map_id != map_id_text
            ):
                trail_points = []
                trail_breaks = []
                trail_path_id = ""
                trail_last_percentage = None
                trail_last_subtotal_area = None
                trail_reset_reason = "mapChanged"

            # A non-zero path-id change is a strong API-level signal for a new
            # route/progress context. Resume normally keeps the same path.
            if (
                trail_enabled
                and path_id_text not in {"", "0"}
                and trail_path_id not in {"", path_id_text}
            ):
                trail_points = []
                trail_breaks = []
                trail_last_percentage = None
                trail_last_subtotal_area = None
                trail_reset_reason = "pathChanged"

            # Navimow offers the user "delete progress/start over" or resume.
            # Preserve the old trail on resume. Only clear it when BOTH public
            # progress measures show a substantial backward reset.
            if (
                trail_enabled
                and trail_points
                and str(
                    runtime_state.get("mqttStatus") or ""
                ).strip().lower() not in {"docked", "isdocked"}
                and _progress_reset_detected(
                    trail_last_percentage,
                    current_percentage,
                    trail_last_subtotal_area,
                    current_subtotal_area,
                )
            ):
                trail_points = []
                trail_reset_reason = "progressReset"

            # Docking closes a trail logically but does not delete it. This is
            # important because the next job may explicitly resume progress.
            if (
                previous_motion_detail == "docked"
                or previous_area == "dock"
            ):
                trail_closed_at_dock = True
            elif trail_points:
                trail_closed_at_dock = False

            if trail_enabled and map_id_text:
                trail_map_id = map_id_text
            if trail_enabled and path_id_text not in {"", "0"}:
                trail_path_id = path_id_text

            if trail_enabled:
                try:
                    mqtt_status_for_trail = str(
                        runtime_state.get("mqttStatus") or ""
                    ).strip().lower()
                    trail_docked = mqtt_status_for_trail in {
                        "docked", "isdocked"
                    }

                    point = [
                        float(normalised_location["postureX"]),
                        float(normalised_location["postureY"]),
                    ]

                    #
                    # Aktuelle Tunnelgeometrie ermitteln.
                    #
                    tunnel_line = None
                    tunnel_distance = None
                    tunnel_start = None
                    tunnel_end = None

                    if map_geometry is not None:
                        tunnels = map_geometry.get("tunnels") or []

                        if tunnels:
                            candidate_line = tunnels[0].get("points") or []

                            if len(candidate_line) >= 2:
                                tunnel_line = candidate_line
                                tunnel_start = candidate_line[0]
                                tunnel_end = candidate_line[-1]
                                tunnel_distance = _trail_polyline_distance(
                                    point,
                                    tunnel_line,
                                )

                    #
                    # Geometrischer Dock-Filter.
                    #
                    # Im unmittelbaren Bereich der Ladestation ist nur der
                    # Korridor VOR dem Dock physikalisch plausibel. Positionen
                    # hinter oder deutlich seitlich der Station werden nicht
                    # in den Trail übernommen.
                    #
                    # Position, Richtung und Breite stammen aus der aktuellen
                    # Navimow-Kartengeometrie; es werden keine Grundstücks-
                    # koordinaten fest codiert.
                    #
                    dock_position_invalid = False

                    if map_geometry is not None:
                        docks = map_geometry.get("docks") or []

                        if docks:
                            dock = docks[0]
                            dock_position = dock.get("position")

                            if (
                                isinstance(dock_position, (list, tuple))
                                and len(dock_position) >= 2
                            ):
                                dock_x = float(dock_position[0])
                                dock_y = float(dock_position[1])
                                dock_direction = float(
                                    dock.get("direction") or 0.0
                                )
                                dock_width = float(
                                    dock.get("width") or 0.56
                                )

                                rel_x = point[0] - dock_x
                                rel_y = point[1] - dock_y

                                dock_radius = math.hypot(
                                    rel_x,
                                    rel_y,
                                )

                                if dock_radius <= 1.6:
                                    cos_dir = math.cos(dock_direction)
                                    sin_dir = math.sin(dock_direction)

                                    dock_forward = (
                                        rel_x * cos_dir
                                        + rel_y * sin_dir
                                    )

                                    dock_lateral = (
                                        -rel_x * sin_dir
                                        + rel_y * cos_dir
                                    )

                                    #
                                    # Etwas Sicherheitsraum gegenüber der
                                    # reinen Dockbreite lassen.
                                    #
                                    corridor_half_width = max(
                                        0.45,
                                        dock_width / 2.0 + 0.20,
                                    )

                                    dock_position_invalid = (
                                        (
                                            dock_forward < -0.15
                                            or abs(dock_lateral)
                                            > corridor_half_width
                                        )
                                        and not (
                                            tunnel_distance is not None
                                            and tunnel_distance <= 0.35
                                        )
                                    )

                    #
                    # Tunnel-Leitplanke.
                    #
                    # Ein Tunnelende allein aktiviert den Filter noch nicht.
                    # Erst wenn sich der nächste Verlauf tatsächlich entlang
                    # der Tunnelachse ins Innere bewegt, wird die Passage aktiv.
                    #
                    tunnel_position_invalid = False

                    if (
                        not dock_position_invalid
                        and tunnel_line is not None
                        and tunnel_start is not None
                        and tunnel_end is not None
                    ):
                        start_distance = math.hypot(
                            point[0] - float(tunnel_start[0]),
                            point[1] - float(tunnel_start[1]),
                        )
                        end_distance = math.hypot(
                            point[0] - float(tunnel_end[0]),
                            point[1] - float(tunnel_end[1]),
                        )

                        entry_radius = 0.35
                        activate_progress = 0.45
                        corridor_width = 0.50
                        exit_radius = 0.45

                        if not trail_tunnel_active:
                            #
                            # An einem Tunnelende: Passage zunächst nur
                            # vormerken.
                            #
                            if trail_tunnel_candidate is None:
                                if start_distance <= entry_radius:
                                    trail_tunnel_candidate = 0
                                elif end_distance <= entry_radius:
                                    trail_tunnel_candidate = 1

                            elif trail_tunnel_candidate == 0:
                                #
                                # Aktivieren erst, wenn wir uns vom Startende
                                # weg und zugleich sauber entlang der
                                # Tunnelachse bewegen.
                                #
                                if (
                                    start_distance >= activate_progress
                                    and tunnel_distance is not None
                                    and tunnel_distance <= 0.35
                                ):
                                    trail_tunnel_active = True
                                    trail_tunnel_target = 1
                                    trail_tunnel_candidate = None
                                elif (
                                    start_distance > 0.80
                                    and (
                                        tunnel_distance is None
                                        or tunnel_distance > 0.35
                                    )
                                ):
                                    trail_tunnel_candidate = None

                            elif trail_tunnel_candidate == 1:
                                if (
                                    end_distance >= activate_progress
                                    and tunnel_distance is not None
                                    and tunnel_distance <= 0.35
                                ):
                                    trail_tunnel_active = True
                                    trail_tunnel_target = 0
                                    trail_tunnel_candidate = None
                                elif (
                                    end_distance > 0.80
                                    and (
                                        tunnel_distance is None
                                        or tunnel_distance > 0.35
                                    )
                                ):
                                    trail_tunnel_candidate = None

                        if trail_tunnel_active:
                            #
                            # Am gegenüberliegenden Ende angekommen:
                            # Leitplanke wieder ausschalten.
                            #
                            target_reached = (
                                (
                                    trail_tunnel_target == 1
                                    and end_distance <= exit_radius
                                )
                                or (
                                    trail_tunnel_target == 0
                                    and start_distance <= exit_radius
                                )
                            )

                            if target_reached:
                                trail_tunnel_active = False
                                trail_tunnel_target = None

                            elif (
                                tunnel_distance is None
                                or tunnel_distance > corridor_width
                            ):
                                #
                                # Während einer bestätigten Passage darf der
                                # Mäher nicht seitlich aus dem Tunnel springen.
                                #
                                tunnel_position_invalid = True

                    if (
                        not dock_position_invalid
                        and not tunnel_position_invalid
                        and len(trail_points) >= 2
                    ):
                        a = trail_points[-2]
                        b = trail_points[-1]
                        ab = math.hypot(b[0] - a[0], b[1] - a[1])
                        bc = math.hypot(point[0] - b[0], point[1] - b[1])
                        ac = math.hypot(point[0] - a[0], point[1] - a[1])

                        global_outlier = (
                            ab > 1.5
                            and bc > 1.5
                            and ac < 1.0
                        )

                        dock_outlier = (
                            abs(a[0]) < 5.0 and abs(a[1]) < 5.0
                            and abs(b[0]) < 5.0 and abs(b[1]) < 5.0
                            and abs(point[0]) < 5.0 and abs(point[1]) < 5.0
                            and ab > 1.2
                            and bc > 1.2
                            and ac < 0.4
                        )

                        if global_outlier or dock_outlier:
                            removed_index = len(trail_points) - 1
                            trail_points.pop()
                            trail_breaks = [
                                x - 1 if x > removed_index else x
                                for x in trail_breaks
                                if x != removed_index
                            ]

                    moved = (
                        not dock_position_invalid
                        and not tunnel_position_invalid
                        and (
                            not trail_points
                            or math.hypot(
                                point[0] - trail_points[-1][0],
                                point[1] - trail_points[-1][1],
                            ) >= trail_min_distance
                        )
                    )
                    # Den ersten Punkt nur als Bezug übernehmen. Ab dem zweiten
                    # ausreichend entfernten Punkt ist die Spur aktiv.
                    if moved and not trail_docked:
                        trail_active = bool(trail_points)
                        if trail_points:
                            jump = math.hypot(
                                point[0] - trail_points[-1][0],
                                point[1] - trail_points[-1][1],
                            )

                            previous_near_zero = (
                                math.hypot(
                                    float(trail_points[-1][0]),
                                    float(trail_points[-1][1]),
                                ) <= 0.15
                            )
                            current_near_zero = (
                                math.hypot(
                                    float(point[0]),
                                    float(point[1]),
                                ) <= 0.15
                            )

                            dock_zero_jump = (
                                jump > 1.5
                                and (previous_near_zero or current_near_zero)
                            )

                            if jump > 4.0 or dock_zero_jump:
                                trail_breaks.append(len(trail_points))
                        trail_points.append(point)
                        if len(trail_points) > trail_max_points:
                            trim_count = len(trail_points) - trail_max_points
                            del trail_points[:trim_count]

                            trail_breaks = [
                                break_index - trim_count
                                for break_index in trail_breaks
                                if break_index > trim_count
                            ]

                        trail_last_percentage = current_percentage
                        trail_last_subtotal_area = current_subtotal_area
                        trail_payload = {
                            "mapId": trail_map_id,
                            "pathId": trail_path_id,
                            "mowingPercentage": trail_last_percentage,
                            "subtotalArea": trail_last_subtotal_area,
                            "breaks": trail_breaks,
                            "trailResetReason": trail_reset_reason,
                            "points": trail_points,
                        }
                        await asyncio.to_thread(
                            _write_json_atomic,
                            trail_file,
                            trail_payload,
                        )
                except (KeyError, TypeError, ValueError):
                    pass

                # Keep reset-detection metadata current even if the mower has
                # not moved far enough to append another trail point.
                if (
                    current_percentage != trail_last_percentage
                    or current_subtotal_area != trail_last_subtotal_area
                ):
                    trail_last_percentage = current_percentage
                    trail_last_subtotal_area = current_subtotal_area
                    trail_payload = {
                        "mapId": trail_map_id,
                        "pathId": trail_path_id,
                        "mowingPercentage": trail_last_percentage,
                        "subtotalArea": trail_last_subtotal_area,
                        "breaks": trail_breaks,
                        "trailResetReason": trail_reset_reason,
                        "points": trail_points,
                    }
                    await asyncio.to_thread(
                        _write_json_atomic,
                        trail_file,
                        trail_payload,
                    )

            normalised_location["trailFile"] = str(trail_file)
            normalised_location["trailPointCount"] = len(trail_points)
            normalised_location["trailSegmentCount"] = 0 if not trail_points else len(trail_breaks) + 1
            normalised_location["trailBreakCount"] = len(trail_breaks)
            normalised_location["trailDistance"] = round(_trail_distance_segmented(trail_points, trail_breaks), 2)
            normalised_location["trailActive"] = 1 if trail_active else 0
            normalised_location["trailResetReason"] = trail_reset_reason
            normalised_location["trailProgressPercentage"] = trail_last_percentage
            normalised_location["trailSubtotalArea"] = trail_last_subtotal_area

            if map_geometry is not None:
                normalised_location["mapSvgFile"] = str(live_svg_file)

            schedule_runtime = _today_plan_runtime_fields(
                plan_state
            )
            normalised_location["scheduleEnabled"] = (
                1 if schedule_runtime.get("available") else 0
            )
            normalised_location["scheduleWeek"] = "aus"
            normalised_location["scheduleToday"] = (
                schedule_runtime.get("today") or "aus"
            )
            normalised_location["scheduleNext"] = (
                schedule_runtime.get("next") or ""
            )
            normalised_location["scheduleNextDate"] = (
                schedule_runtime.get("nextDate") or ""
            )
            normalised_location["scheduleNextDay"] = (
                schedule_runtime.get("nextDay") or ""
            )
            normalised_location["scheduleNextStart"] = (
                schedule_runtime.get("nextStart") or ""
            )
            normalised_location["scheduleNextEnd"] = (
                schedule_runtime.get("nextEnd") or ""
            )
            normalised_location["scheduleNextInMinutes"] = (
                schedule_runtime.get("nextInMinutes")
            )
            normalised_location["planStatus"] = plan_state.get("c_plan_status")
            normalised_location["taskStatus"] = plan_state.get("m_task_status")
            normalised_location["planStartTime"] = plan_state.get("c_plan_s_time")
            normalised_location["planEndTime"] = plan_state.get("c_plan_e_time")
            normalised_location["planWeekDay"] = plan_state.get("weekDay")

            mowing_stats_location = _mowing_history_statistics(
                mowing_history_file
            )
            mowing_stats_last_location = (
                mowing_stats_location.get("last") or {}
            )

            for source_key, target_key in (
                ("todayRuns", "statsTodayRuns"),
                ("todayMowingSeconds", "statsTodayMowingSeconds"),
                ("todayDurationSeconds", "statsTodayDurationSeconds"),
                ("todayDistanceM", "statsTodayDistanceM"),
                ("todayAreaM2", "statsTodayAreaM2"),
                ("weekRuns", "statsWeekRuns"),
                ("weekMowingSeconds", "statsWeekMowingSeconds"),
                ("weekDurationSeconds", "statsWeekDurationSeconds"),
                ("weekDistanceM", "statsWeekDistanceM"),
                ("weekAreaM2", "statsWeekAreaM2"),
                ("monthRuns", "statsMonthRuns"),
                ("monthMowingSeconds", "statsMonthMowingSeconds"),
                ("monthDurationSeconds", "statsMonthDurationSeconds"),
                ("monthDistanceM", "statsMonthDistanceM"),
                ("monthAreaM2", "statsMonthAreaM2"),
            ):
                normalised_location[target_key] = mowing_stats_location.get(
                    source_key, 0
                )

            for source_key, target_key in (
                ("startedAt", "statsLastStartedAt"),
                ("mowingEndedAt", "statsLastMowingEndedAt"),
                ("endedAt", "statsLastEndedAt"),
                ("mowingSeconds", "statsLastMowingSeconds"),
                ("durationSeconds", "statsLastDurationSeconds"),
                ("distanceM", "statsLastDistanceM"),
                ("areaM2", "statsLastAreaM2"),
                ("progressPercent", "statsLastProgressPercent"),
                ("result", "statsLastResult"),
            ):
                normalised_location[target_key] = (
                    mowing_stats_last_location.get(source_key)
                )

            emit(
                "location",
                deviceId=device_id,
                data=normalised_location,
            )

            model.update_location(normalised_location)
            model_snapshot = model.snapshot()
            current_motion_detail = str(
                model_snapshot.get("motion_detail") or ""
            ).lower()
            current_geometry = model_snapshot.get("geometry") or {}
            current_area = str(
                current_geometry.get("location_area") or ""
            ).lower()

            # For mowing-session history the real-time MQTT state is
            # authoritative. model motion_detail describes physical motion
            # and may remain standing while a mowing task is active.
            mqtt_history_motion = str(
                runtime_state.get("mqttStatus") or ""
            ).strip().lower()
            if mqtt_history_motion in {
                "mowing", "paused", "returning", "docked", "idle"
            }:
                history_motion = mqtt_history_motion
            else:
                history_motion = current_motion_detail

            history_now = time.time()

            if history_motion == "mowing":
                if mowing_session is None:
                    mowing_session = {
                        "version": 1,
                        "startedAt": history_now,
                        "lastMowingAt": history_now,
                        "mowingSeconds": 0.0,
                        "mowingEndedAt": None,
                        "startAreaM2": normalised_location.get("subtotalArea"),
                        "lastAreaM2": normalised_location.get("subtotalArea"),
                        "startDistanceM": round(_trail_distance_segmented(trail_points, trail_breaks), 2),
                        "lastDistanceM": round(_trail_distance_segmented(trail_points, trail_breaks), 2),
                        "progressPercent": normalised_location.get("mowingPercentage"),
                        "planStatusStart": plan_state.get("c_plan_status"),
                        "taskStatusStart": plan_state.get("m_task_status"),
                        "planStartTime": plan_state.get("c_plan_s_time"),
                        "planEndTime": plan_state.get("c_plan_e_time"),
                        "planWeekDay": plan_state.get("weekDay"),
                    }
                else:
                    last_mowing_at = mowing_session.get("lastMowingAt")
                    if previous_history_motion == "mowing" and last_mowing_at is not None:
                        try:
                            mowing_session["mowingSeconds"] = (
                                float(mowing_session.get("mowingSeconds") or 0.0)
                                + max(0.0, history_now - float(last_mowing_at))
                            )
                        except (TypeError, ValueError):
                            pass
                    mowing_session["lastMowingAt"] = history_now
                    mowing_session["mowingEndedAt"] = None

                mowing_session["lastAreaM2"] = normalised_location.get("subtotalArea")
                mowing_session["lastDistanceM"] = round(_trail_distance_segmented(trail_points, trail_breaks), 2)
                mowing_session["progressPercent"] = normalised_location.get("mowingPercentage")
                mowing_session["planStatusLast"] = plan_state.get("c_plan_status")
                mowing_session["taskStatusLast"] = plan_state.get("m_task_status")
                mowing_session["planStartTimeLast"] = plan_state.get("c_plan_s_time")
                mowing_session["planEndTimeLast"] = plan_state.get("c_plan_e_time")
                await asyncio.to_thread(_write_json_atomic, mowing_session_file, mowing_session)

            elif mowing_session is not None:
                if previous_history_motion == "mowing":
                    last_mowing_at = mowing_session.get("lastMowingAt")
                    if last_mowing_at is not None:
                        try:
                            mowing_session["mowingSeconds"] = (
                                float(mowing_session.get("mowingSeconds") or 0.0)
                                + max(0.0, history_now - float(last_mowing_at))
                            )
                        except (TypeError, ValueError):
                            pass

                mowing_session["lastMowingAt"] = None
                mowing_session["lastAreaM2"] = normalised_location.get("subtotalArea")
                mowing_session["lastDistanceM"] = round(_trail_distance_segmented(trail_points, trail_breaks), 2)
                mowing_session["progressPercent"] = normalised_location.get("mowingPercentage")
                mowing_session["planStatusLast"] = plan_state.get("c_plan_status")
                mowing_session["taskStatusLast"] = plan_state.get("m_task_status")
                mowing_session["planStartTimeLast"] = plan_state.get("c_plan_s_time")
                mowing_session["planEndTimeLast"] = plan_state.get("c_plan_e_time")

                if history_motion == "returning" and not mowing_session.get("mowingEndedAt"):
                    mowing_session["planStatusAtReturn"] = plan_state.get("c_plan_status")
                    mowing_session["taskStatusAtReturn"] = plan_state.get("m_task_status")
                    mowing_session["planStartTimeAtReturn"] = plan_state.get("c_plan_s_time")
                    mowing_session["planEndTimeAtReturn"] = plan_state.get("c_plan_e_time")
                    mowing_session["mowingEndedAt"] = history_now

                if history_motion == "docked" or current_area == "dock":
                    if not mowing_session.get("mowingEndedAt"):
                        mowing_session["mowingEndedAt"] = history_now

                    started_at = float(mowing_session.get("startedAt") or history_now)

                    start_area = mowing_session.get("startAreaM2")
                    last_area = mowing_session.get("lastAreaM2")
                    try:
                        area_m2 = max(0.0, float(last_area) - float(start_area))
                    except (TypeError, ValueError):
                        try:
                            area_m2 = max(0.0, float(last_area))
                        except (TypeError, ValueError):
                            area_m2 = 0.0

                    try:
                        distance_m = max(
                            0.0,
                            float(mowing_session.get("lastDistanceM") or 0.0)
                            - float(mowing_session.get("startDistanceM") or 0.0),
                        )
                    except (TypeError, ValueError):
                        distance_m = 0.0

                    record = {
                        "version": 1,
                        "startedAt": started_at,
                        "mowingEndedAt": float(mowing_session.get("mowingEndedAt") or history_now),
                        "endedAt": history_now,
                        "durationSeconds": round(max(0.0, history_now - started_at), 1),
                        "mowingSeconds": round(max(0.0, float(mowing_session.get("mowingSeconds") or 0.0)), 1),
                        "areaM2": round(area_m2, 2),
                        "distanceM": round(distance_m, 2),
                        "progressPercent": mowing_session.get("progressPercent"),
                        "planStatusStart": mowing_session.get("planStatusStart"),
                        "taskStatusStart": mowing_session.get("taskStatusStart"),
                        "planStartTime": mowing_session.get("planStartTime"),
                        "planEndTime": mowing_session.get("planEndTime"),
                        "planWeekDay": mowing_session.get("planWeekDay"),
                        "planStatusAtReturn": mowing_session.get("planStatusAtReturn"),
                        "taskStatusAtReturn": mowing_session.get("taskStatusAtReturn"),
                        "planStatusLast": mowing_session.get("planStatusLast"),
                        "taskStatusLast": mowing_session.get("taskStatusLast"),
                        "endState": "docked",
                        "result": "docked",
                    }
                    await asyncio.to_thread(_append_mowing_history, mowing_history_file, record)
                    try:
                        mowing_session_file.unlink(missing_ok=True)
                    except Exception:
                        pass
                    mowing_session = None
                else:
                    await asyncio.to_thread(_write_json_atomic, mowing_session_file, mowing_session)

            previous_history_motion = history_motion

            if trail_points and (
                current_motion_detail == "docked" or current_area == "dock"
            ):
                trail_closed_at_dock = True

            render_ms = 0.0
            svg_write_ms = 0.0
            if map_geometry is not None:
                render_started = loop_clock.time()
                renderer_frame = build_renderer_frame(
                    model_snapshot,
                    map_geometry,
                    trail={"points": trail_points, "breaks": trail_breaks},
                    force_docked=(
                        str(runtime_state.get("mqttStatus") or "").lower()
                        == "docked"
                    ),
                    metadata={
                        "deviceId": device_id,
                        "vehicleSn": vehicle_sn,
                        "bridgeVersion": BRIDGE_VERSION,
                    },
                )
                live_svg = live_svg_renderer.render(renderer_frame)
                live_base_svg = live_svg_renderer.render(
                    renderer_frame,
                    include_mower=False,
                )
                mower_screen_state = live_svg_renderer.mower_screen_state(
                    renderer_frame
                )
                render_ms = (loop_clock.time() - render_started) * 1000.0

                write_started = loop_clock.time()
                await asyncio.to_thread(
                    _write_text_atomic,
                    live_svg_file,
                    live_svg,
                    0o644,
                )
                await asyncio.to_thread(
                    _write_text_atomic,
                    live_base_svg_file,
                    live_base_svg,
                    0o644,
                )

                if mower_screen_state is not None:
                    battery_soc = battery_state.get("soc")
                    battery_charge_limit = battery_limits.get("chargingLimit")
                    battery_return_level = battery_limits.get(
                        "returnBatteryLevel"
                    )
                    battery_window_percent = None
                    try:
                        soc_value = float(battery_soc)
                        low_value = float(battery_return_level)
                        high_value = float(battery_charge_limit)
                        if high_value > low_value:
                            battery_window_percent = max(
                                0.0,
                                min(
                                    100.0,
                                    (
                                        (soc_value - low_value)
                                        / (high_value - low_value)
                                    )
                                    * 100.0,
                                ),
                            )
                    except (TypeError, ValueError):
                        pass

                    schedule_runtime = _today_plan_runtime_fields(
                        plan_state
                    )
                    mowing_stats = _mowing_history_statistics(
                        mowing_history_file
                    )
                    mowing_stats_last = mowing_stats.get("last") or {}

                    state_payload = {
                        **mower_screen_state,
                        "sourceTimestamp": float(
                            normalised_location.get("timestamp")
                            or time.time()
                        ),
                        "generatedAt": time.time(),
                        "motion": str(
                            model_snapshot.get("motion_detail") or ""
                        ),
                        "area": str(
                            (model_snapshot.get("geometry") or {}).get(
                                "location_area"
                            )
                            or ""
                        ),
                        "mowingPercentage": normalised_location.get(
                            "mowingPercentage"
                        ),
                        "mowingWeekArea": normalised_location.get(
                            "mowingWeekArea"
                        ),
                        "subtotalArea": normalised_location.get(
                            "subtotalArea"
                        ),
                        "batterySoc": battery_soc,
                        "batterySoh": battery_state.get("soh"),
                        "batteryStatus": battery_state.get(
                            "batteryStatus"
                        ),
                        "chargeRemainMinutes": battery_state.get(
                            "chgRemainTimeUser"
                        ),
                        "batteryChargeLimit": battery_charge_limit,
                        "batteryReturnLevel": battery_return_level,
                        "batteryWindowPercent": (
                            round(battery_window_percent, 1)
                            if battery_window_percent is not None
                            else None
                        ),
                        "networkType": battery_state.get("networkType"),
                        "networkStatus": battery_state.get("networkStatus"),
                        "networkSignal": battery_state.get("networkSignal"),
                        "networkSignal4G": battery_state.get("networkSignal4G"),
                        "networkSignalWifi": battery_state.get("networkSignalWifi"),
                        "mqttState": runtime_state.get("mqttStatus") or "",
                        "mqttStateRaw": runtime_state.get("mqttStatusRaw") or "",
                        "mqttBattery": runtime_state.get("mqttBattery"),
                        "mqttTimestamp": runtime_state.get("mqttTimestamp"),
                        "mqttIgnoredStateRaw": runtime_state.get("mqttIgnoredStateRaw") or "",
                        "mqttIgnoredTimestamp": runtime_state.get("mqttIgnoredTimestamp"),
                        "state": (
                            "docked"
                            if str(model_snapshot.get("motion_detail") or "").lower() == "docked"
                            else (runtime_state.get("mqttStatus") or "")
                        ),
                        "mqttStatus": runtime_state.get("mqttStatus") or "",
                        "mqttStatusTimestamp": runtime_state.get("mqttStatusTimestamp"),
                        "privatePollMode": runtime_state.get("privatePollMode") or "",
                        "privatePollIntervalCurrent": runtime_state.get("privatePollIntervalCurrent"),
                        "scheduleEnabled": bool(schedule_runtime.get("available")),
                        "scheduleWeek": "aus",
                        "scheduleDays": [],
                        "scheduleToday": schedule_runtime.get("today") or "aus",
                        "scheduleNext": schedule_runtime.get("next") or "",
                        "scheduleNextDate": schedule_runtime.get("nextDate") or "",
                        "scheduleNextDay": schedule_runtime.get("nextDay") or "",
                        "scheduleNextStart": schedule_runtime.get("nextStart") or "",
                        "scheduleNextEnd": schedule_runtime.get("nextEnd") or "",
                        "scheduleNextInMinutes": schedule_runtime.get("nextInMinutes"),
                        "planStatus": plan_state.get("c_plan_status"),
                        "taskStatus": plan_state.get("m_task_status"),
                        "planStartTime": plan_state.get("c_plan_s_time"),
                        "planEndTime": plan_state.get("c_plan_e_time"),
                        "partitionLength": plan_state.get("partition_length"),
                        "partitionDetail": plan_state.get("partition_detail"),
                        "planDiagnosticFile": str(plan_diagnostic_file),
                        "mowingHistoryFile": str(mowing_history_file),
                        "mowingSessionFile": str(mowing_session_file),
                        "mowingSessionActive": bool(mowing_session),

                        "statsTodayRuns": mowing_stats.get("todayRuns", 0),
                        "statsTodayMowingSeconds": mowing_stats.get("todayMowingSeconds", 0.0),
                        "statsTodayDurationSeconds": mowing_stats.get("todayDurationSeconds", 0.0),
                        "statsTodayDistanceM": mowing_stats.get("todayDistanceM", 0.0),
                        "statsTodayAreaM2": mowing_stats.get("todayAreaM2", 0.0),

                        "statsWeekRuns": mowing_stats.get("weekRuns", 0),
                        "statsWeekMowingSeconds": mowing_stats.get("weekMowingSeconds", 0.0),
                        "statsWeekDurationSeconds": mowing_stats.get("weekDurationSeconds", 0.0),
                        "statsWeekDistanceM": mowing_stats.get("weekDistanceM", 0.0),
                        "statsWeekAreaM2": mowing_stats.get("weekAreaM2", 0.0),

                        "statsMonthRuns": mowing_stats.get("monthRuns", 0),
                        "statsMonthMowingSeconds": mowing_stats.get("monthMowingSeconds", 0.0),
                        "statsMonthDurationSeconds": mowing_stats.get("monthDurationSeconds", 0.0),
                        "statsMonthDistanceM": mowing_stats.get("monthDistanceM", 0.0),
                        "statsMonthAreaM2": mowing_stats.get("monthAreaM2", 0.0),

                        "statsLastStartedAt": mowing_stats_last.get("startedAt"),
                        "statsLastMowingEndedAt": mowing_stats_last.get("mowingEndedAt"),
                        "statsLastEndedAt": mowing_stats_last.get("endedAt"),
                        "statsLastMowingSeconds": mowing_stats_last.get("mowingSeconds"),
                        "statsLastDurationSeconds": mowing_stats_last.get("durationSeconds"),
                        "statsLastDistanceM": mowing_stats_last.get("distanceM"),
                        "statsLastAreaM2": mowing_stats_last.get("areaM2"),
                        "statsLastProgressPercent": mowing_stats_last.get("progressPercent"),
                        "statsLastResult": mowing_stats_last.get("result") or "",

                        "icon": str(
                            configuration.get("privateLiveMowerIcon", "")
                            or ""
                        ),
                    }
                    state_js = (
                        "window.NavimowSmoothLive&&"
                        "window.NavimowSmoothLive.push("
                        + json.dumps(
                            state_payload,
                            ensure_ascii=False,
                            separators=(",", ":"),
                        )
                        + ");\n"
                    )
                    await asyncio.to_thread(
                        _write_text_atomic,
                        live_state_js_file,
                        state_js,
                        0o644,
                    )

                svg_write_ms = (loop_clock.time() - write_started) * 1000.0

            model_events = event_engine.process(model_snapshot)
            history_engine.append(model_snapshot, model_events)
            timeline_timestamp = float(
                model_snapshot.get("last_update") or time.time()
            )
            event_timeline_engine.append(
                timeline_timestamp,
                model_events,
            )
            timeline_entry = timeline_engine.append(
                timeline_timestamp,
                model_snapshot,
                model_events,
            )
            compact_state = compact_snapshot(model_snapshot)
            compact_state["historySize"] = history_engine.size
            compact_state["eventSequence"] = event_engine.sequence
            compact_state["timelineSize"] = timeline_engine.size
            compact_state["timelineSequence"] = timeline_entry.sequence
            compact_state["eventTimelineSize"] = event_timeline_engine.size
            compact_state["eventTimelineSequence"] = event_timeline_engine.sequence
            compact_state["liveSvgFile"] = str(live_svg_file)
            compact_state["liveSvgWidth"] = live_svg_width
            compact_state["liveSvgHeight"] = live_svg_height
            compact_state["liveSvgZoom"] = live_zoom
            compact_state["liveSvgPanX"] = live_pan_x
            compact_state["liveSvgPanY"] = live_pan_y

            timeline_payload = {
                "version": 1,
                "generatedAt": time.time(),
                "size": timeline_engine.size,
                "sequence": timeline_engine.sequence,
                "maxEntries": timeline_engine.max_entries,
                "entries": timeline_engine.snapshot(timeline_export_count),
            }
            await asyncio.to_thread(
                _write_json_atomic,
                timeline_file,
                timeline_payload,
            )

            event_timeline_payload = {
                "version": 1,
                "generatedAt": time.time(),
                "size": event_timeline_engine.size,
                "sequence": event_timeline_engine.sequence,
                "maxEntries": event_timeline_engine.max_entries,
                "entries": event_timeline_engine.snapshot(
                    event_timeline_export_count
                ),
            }
            await asyncio.to_thread(
                _write_json_atomic,
                event_timeline_file,
                event_timeline_payload,
            )

            emit(
                "modelState",
                deviceId=device_id,
                data=compact_state,
            )
            for model_event in model_events:
                emit(
                    "modelEvent",
                    deviceId=device_id,
                    event=model_event.name,
                    timestamp=model_event.timestamp,
                    data=model_event.data,
                )

            map_id = location.get("map_id")
            map_base_id = location.get("map_base_id")
            map_key = (str(map_id), str(map_base_id))
            now = asyncio.get_running_loop().time()

            if (
                map_enabled
                and map_id not in (None, "")
                and map_base_id not in (None, "")
                and map_key != loaded_map_key
                and now >= next_map_retry
            ):
                emit(
                    "mapDetail",
                    deviceId=device_id,
                    state="loading",
                    mapId=str(map_id),
                    mapBaseId=str(map_base_id),
                    file=str(map_file),
                )

                try:
                    map_detail = await asyncio.to_thread(
                        client.map_detail_plain,
                        vehicle_sn,
                        str(map_id),
                        str(map_base_id),
                    )
                    await asyncio.to_thread(private_session.sync_from_client, client)
                    file_bytes = await asyncio.to_thread(
                        _write_json_atomic,
                        map_file,
                        map_detail,
                    )
                    map_geometry = _extract_map_geometry(map_detail)
                    model.update_geometry(map_geometry)
                    refreshed_snapshot = model.snapshot()

                    renderer_frame = build_renderer_frame(
                        refreshed_snapshot,
                        map_geometry,
                        trail=trail_points,
                        metadata={
                            "deviceId": device_id,
                            "vehicleSn": vehicle_sn,
                            "bridgeVersion": BRIDGE_VERSION,
                        },
                    )
                    live_svg = live_svg_renderer.render(renderer_frame)
                    live_base_svg = live_svg_renderer.render(
                        renderer_frame,
                        include_mower=False,
                    )
                    svg_bytes = await asyncio.to_thread(
                        _write_text_atomic,
                        live_svg_file,
                        live_svg,
                        0o644,
                    )
                    await asyncio.to_thread(
                        _write_text_atomic,
                        live_base_svg_file,
                        live_base_svg,
                        0o644,
                    )

                    # A freshly loaded map changes interpretation, not the mower's
                    # physical state. Use it as a new event baseline to avoid
                    # synthetic zone/dock events during startup.
                    event_engine.reset(refreshed_snapshot)
                    compact_state = compact_snapshot(refreshed_snapshot)
                    compact_state["historySize"] = history_engine.size
                    compact_state["eventSequence"] = event_engine.sequence
                    compact_state["timelineSize"] = timeline_engine.size
                    compact_state["timelineSequence"] = timeline_engine.sequence
                    compact_state["eventTimelineSize"] = event_timeline_engine.size
                    compact_state["eventTimelineSequence"] = event_timeline_engine.sequence
                    compact_state["liveSvgFile"] = str(live_svg_file)
                    compact_state["liveSvgWidth"] = live_svg_width
                    compact_state["liveSvgHeight"] = live_svg_height
                    compact_state["liveSvgZoom"] = live_zoom
                    compact_state["liveSvgPanX"] = live_pan_x
                    compact_state["liveSvgPanY"] = live_pan_y
                    emit(
                        "modelState",
                        deviceId=device_id,
                        data=compact_state,
                    )
                    geometry_bytes = await asyncio.to_thread(
                        _write_json_atomic, geometry_file, map_geometry
                    )
                    loaded_map_key = map_key
                    next_map_retry = 0.0
                    emit(
                        "mapDetail",
                        deviceId=device_id,
                        state="stored",
                        mapId=str(map_id),
                        mapBaseId=str(map_base_id),
                        file=str(map_file),
                        fileBytes=file_bytes,
                        geometryFile=str(geometry_file),
                        geometryBytes=geometry_bytes,
                        svgFile=str(live_svg_file),
                        svgBytes=svg_bytes,
                        zoneCount=len(map_geometry.get("zones", [])),
                        zones=[
                            {
                                "id": str(zone.get("id") or ""),
                                "name": str(zone.get("name") or ""),
                            }
                            for zone in map_geometry.get("zones", [])
                            if isinstance(zone, dict)
                        ],
                        obstacleCount=len(map_geometry.get("obstacles", [])),
                        tunnelCount=len(map_geometry.get("tunnels", [])),
                        visionOffAreaCount=len(map_geometry.get("visionOffAreas", [])),
                        dockCount=len(map_geometry.get("docks", [])),
                        bounds=map_geometry.get("bounds"),
                        **_map_detail_summary(map_detail),
                    )
                except asyncio.CancelledError:
                    raise
                except Exception as error:
                    next_map_retry = now + 60.0
                    safe_message = redact(str(error), secrets)
                    emit(
                        "error",
                        stage="privateMapDetail",
                        deviceId=device_id,
                        message=safe_message,
                        mapId=str(map_id),
                        mapBaseId=str(map_base_id),
                    )
                    log("Navimow: Kartendetail-Abfrage fehlgeschlagen:")
                    traceback.print_exc(file=sys.stderr)

            if consecutive_errors:
                emit(
                    "privateCloudState",
                    deviceId=device_id,
                    state="connected",
                    message="location polling recovered",
                )

            now_monotonic = loop_clock.time()
            mqtt_status = str(runtime_state.get("mqttStatus") or "").lower()
            motion_detail = str(
                model_snapshot.get("motion_detail") or ""
            ).lower()
            location_area = str(
                (model_snapshot.get("geometry") or {}).get("location_area")
                or ""
            ).lower()

            soc_value = battery_state.get("soc")
            limit_value = battery_limits.get("chargingLimit")
            try:
                soc_number = float(soc_value)
            except (TypeError, ValueError):
                soc_number = None
            try:
                limit_number = float(limit_value)
            except (TypeError, ValueError):
                limit_number = None

            physically_docked = (
                motion_detail == "docked" or location_area == "dock"
            )

            if now_monotonic < fast_poll_until:
                current_poll_interval = poll_interval_active
                current_poll_mode = "command"
            elif mqtt_status == "mowing":
                current_poll_interval = poll_interval_active
                current_poll_mode = "mowing"
            elif mqtt_status == "returning":
                current_poll_interval = poll_interval_returning
                current_poll_mode = "returning"
            elif mqtt_status == "paused":
                current_poll_interval = poll_interval_paused
                current_poll_mode = "paused"
            elif physically_docked:
                parked = (
                    soc_number is not None
                    and limit_number is not None
                    and limit_number > 0
                    and soc_number >= limit_number
                )
                if parked:
                    current_poll_interval = poll_interval_docked_parked
                    current_poll_mode = "parked"
                else:
                    current_poll_interval = poll_interval_docked_charging
                    current_poll_mode = "charging"
            elif mqtt_status:
                current_poll_interval = poll_interval_transition
                current_poll_mode = "transition"
            else:
                current_poll_interval = max(
                    poll_interval_transition,
                    poll_interval_base,
                )
                current_poll_mode = "unknown"

            runtime_state["privatePollIntervalCurrent"] = current_poll_interval
            runtime_state["privatePollMode"] = current_poll_mode

            loop_ms = (loop_clock.time() - iteration_started) * 1000.0
            sleep_ms = max(
                0.0,
                current_poll_interval * 1000.0 - loop_ms,
            )

            if diagnostics_enabled:
                await asyncio.to_thread(
                    _append_jsonl_bounded,
                    diagnostics_file,
                    {
                        "timestamp": time.time(),
                        "requestMs": round(request_ms, 1),
                        "renderMs": round(render_ms, 1),
                        "svgWriteMs": round(svg_write_ms, 1),
                        "loopMs": round(loop_ms, 1),
                        "sleepMs": round(sleep_ms, 1),
                        "pollIntervalSeconds": round(current_poll_interval, 1),
                        "pollMode": current_poll_mode,
                        "positionChanged": bool(position_changed),
                        "positionChangeIntervalMs": (
                            None
                            if position_change_interval_ms is None
                            else round(position_change_interval_ms, 1)
                        ),
                        "x": None if position_signature is None else position_signature[0],
                        "y": None if position_signature is None else position_signature[1],
                        "theta": None if position_signature is None else position_signature[2],
                    },
                )

            consecutive_errors = 0

        except asyncio.CancelledError:
            raise

        except Exception as error:
            consecutive_errors += 1
            safe_message = redact(str(error), secrets)
            emit(
                "error",
                stage="privateLocation",
                deviceId=device_id,
                message=safe_message,
                consecutiveErrors=consecutive_errors,
            )
            log("Navimow: Standortabfrage fehlgeschlagen:")
            traceback.print_exc(file=sys.stderr)

        elapsed = asyncio.get_running_loop().time() - iteration_started
        await asyncio.sleep(
            max(0.0, current_poll_interval - elapsed)
        )


async def run_bridge(configuration: dict[str, Any]) -> None:
    """Run private cloud and optional MQTT status channel in parallel."""

    device_id = str(configuration["deviceId"]).strip()
    access_token = str(configuration.get("accessToken", "")).strip()
    api_base_url = str(
        configuration.get("apiBaseUrl", "https://navimow-fra.ninebot.com")
    ).strip()
    mqtt_enabled = str(
        configuration.get("mqttEnabled", True)
    ).strip().lower() not in {"0", "false", "no", "off", ""}
    mqtt_host = str(configuration.get("mqttHost", "")).strip()
    mqtt_url = str(configuration.get("mqttUrl", "")).strip()
    mqtt_user = str(configuration.get("mqttUser", "")).strip()
    mqtt_password = str(configuration.get("mqttPassword", "")).strip()

    secrets = [
        access_token,
        mqtt_password,
        str(configuration.get("privateEmail", "")),
        str(configuration.get("privatePassword", "")),
    ]

    event_loop = asyncio.get_running_loop()
    bridge_start_time = event_loop.time()
    runtime_state: dict[str, Any] = {
        "status": "hybrid",
        "commandQueue": asyncio.Queue(),
        "mqttStatus": str(configuration.get("bridgeInitialState", "") or "").strip().lower(),
        "mqttStatusTimestamp": None,
        "mqttStatusRaw": "",
        "mqttBattery": None,
        "mqttTimestamp": None,
        "mqttLastAcceptedTimestamp": None,
        "mqttIgnoredStateRaw": "",
        "mqttIgnoredTimestamp": None,
    }

    client_path = str(configuration.get(
        "privateClientPath", "/opt/fhem/navimow-python"
    )).strip()
    if client_path and client_path not in sys.path:
        sys.path.insert(0, client_path)

    component_versions: dict[str, str] = {
        "project": PROJECT_VERSION,
        "bridge": BRIDGE_VERSION,
        "model": "unknown",
        "geometry": "unknown",
        "motion": "unknown",
        "snapshot": "unknown",
        "events": "unknown",
        "history": "unknown",
        "timeline": "unknown",
        "eventTimeline": "unknown",
        "rendererApi": "unknown",
        "rendererSvg": "unknown",
    }
    try:
        from navimow_private.model import MODULE_VERSION as model_version
        from navimow_private.geometry import MODULE_VERSION as geometry_version
        from navimow_private.motion import MODULE_VERSION as motion_version
        from navimow_private.snapshot import MODULE_VERSION as snapshot_version
        from navimow_private.events import MODULE_VERSION as events_version
        from navimow_private.history import MODULE_VERSION as history_version
        from navimow_private.timeline import MODULE_VERSION as timeline_version
        from navimow_private.event_timeline import MODULE_VERSION as event_timeline_version
        from navimow_private.renderer_api import MODULE_VERSION as renderer_api_version
        from navimow_private.renderer_svg import MODULE_VERSION as renderer_svg_version

        component_versions.update({
            "model": model_version,
            "geometry": geometry_version,
            "motion": motion_version,
            "snapshot": snapshot_version,
            "events": events_version,
            "history": history_version,
            "timeline": timeline_version,
            "eventTimeline": event_timeline_version,
            "rendererApi": renderer_api_version,
            "rendererSvg": renderer_svg_version,
        })
    except Exception:
        log("Navimow: Ermittlung der Komponentenversionen fehlgeschlagen:")
        traceback.print_exc(file=sys.stderr)

    async def command_input_loop() -> None:
        command_queue = runtime_state["commandQueue"]
        while True:
            line = await asyncio.to_thread(sys.stdin.readline)
            if not line:
                return
            line = line.strip()
            if not line:
                continue
            try:
                command = json.loads(line)
                if not isinstance(command, dict):
                    raise ValueError("runtime command must be a JSON object")
                await command_queue.put(command)
            except Exception as error:
                emit("commandResult", deviceId=device_id, requestId="",
                     command="", ok=False,
                     message=f"ungültiger Laufzeitbefehl: {error}")

    async def heartbeat_loop() -> None:
        sequence = 0
        while True:
            await asyncio.sleep(60)
            sequence += 1
            emit("heartbeat", deviceId=device_id, sequence=sequence,
                 uptimeSeconds=int(event_loop.time() - bridge_start_time))

    last_status_fingerprint = None
    last_status_time = 0.0

    def status_callback(status: DeviceStatus) -> None:
        nonlocal last_status_fingerprint, last_status_time
        try:
            data = status.to_dict()
            runtime_state["mqttStatus"] = str(data.get("status") or "").strip().lower()
            runtime_state["mqttStatusRaw"] = str(data.get("status_raw") or "").strip()
            runtime_state["mqttBattery"] = data.get("battery")
            runtime_state["mqttTimestamp"] = data.get("timestamp")
            runtime_state["mqttStatusTimestamp"] = time.time()
            now = event_loop.time()
            fingerprint = (
                data.get("status"),
                data.get("battery"),
                data.get("error_code"),
            )
            if (
                last_status_fingerprint is not None
                and fingerprint == last_status_fingerprint
                and now - last_status_time < 1.0
            ):
                return
            last_status_fingerprint = fingerprint
            last_status_time = now
            emit("status", deviceId=status.device_id or device_id, data=data)
        except Exception as error:
            emit("error", stage="statusCallback", deviceId=device_id,
                 message=redact(str(error), secrets))

    async def mqtt_loop() -> None:
        """Connect directly to Navimow MQTT using credentials from FHEM."""
        if not all((mqtt_host, mqtt_url, mqtt_user, mqtt_password)):
            raise RuntimeError("incomplete MQTT credentials from FHEM")

        scheme = "wss"
        host = mqtt_host
        if "://" in host:
            scheme, host = host.split("://", 1)
            scheme = scheme.lower()
        port = 443 if scheme == "wss" else 80
        if ":" in host and host.rsplit(":", 1)[1].isdigit():
            host, port_text = host.rsplit(":", 1)
            port = int(port_text)

        path = mqtt_url
        if "://" in path:
            path = "/" + path.split("/", 3)[3] if path.count("/") >= 3 else "/mqtt"
        if not path.startswith("/"):
            path = "/" + path

        client_id = f"fhem_{device_id}_{int(time.time())}"
        connected = asyncio.Event()
        failed = asyncio.Event()
        failure = {"message": ""}

        mqtt_client = paho_mqtt.Client(
            callback_api_version=paho_mqtt.CallbackAPIVersion.VERSION2,
            client_id=client_id,
            transport="websockets",
            protocol=paho_mqtt.MQTTv311,
        )

        mqtt_client.username_pw_set(mqtt_user, mqtt_password)
        headers = {"Authorization": "Bearer " + access_token} if access_token else None
        mqtt_client.ws_set_options(path=path, headers=headers)
        if scheme == "wss":
            mqtt_client.tls_set()

        topics = [
            f"/downlink/vehicle/{device_id}/realtimeDate/state",
            f"/downlink/vehicle/{device_id}/realtimeDate/event",
            f"/downlink/vehicle/{device_id}/realtimeDate/attributes",
        ]

        def on_connect(
            client: Any,
            userdata: Any,
            connect_flags: Any,
            reason_code: Any,
            properties: Any,
        ) -> None:
            rc_value = getattr(reason_code, "value", reason_code)
            if int(rc_value) != 0:
                failure["message"] = f"MQTT connect rc={rc_value}"
                event_loop.call_soon_threadsafe(failed.set)
                return
            emit("mqttState", deviceId=device_id, state="connected", broker=f"{host}:{port}", path=path)
            for topic in topics:
                result = client.subscribe(topic, qos=0)
                emit("mqttSubscribe", deviceId=device_id, topic=topic, result=list(result) if isinstance(result, tuple) else str(result))
            event_loop.call_soon_threadsafe(connected.set)

        def on_subscribe(
            client: Any,
            userdata: Any,
            mid: Any,
            reason_code_list: Any,
            properties: Any,
        ) -> None:
            try:
                qos_values = [
                    getattr(reason_code, "value", reason_code)
                    for reason_code in (reason_code_list or [])
                ]
            except Exception:
                qos_values = [str(reason_code_list)]
            emit("mqttSuback", deviceId=device_id, mid=mid, grantedQos=qos_values)

        def on_message(client: Any, userdata: Any, message: Any) -> None:
            try:
                payload_text = (
                    message.payload.decode("utf-8", errors="replace")
                    if isinstance(message.payload, bytes)
                    else str(message.payload)
                )
                payload_data = json.loads(payload_text)
                if not isinstance(payload_data, dict):
                    return

                topic = str(message.topic)
                if not topic.endswith("/realtimeDate/state"):
                    return

                raw_state = str(payload_data.get("state") or "").strip()
                raw_timestamp = payload_data.get("timestamp")

                try:
                    timestamp_value = int(raw_timestamp)
                except (TypeError, ValueError):
                    timestamp_value = None

                last_accepted = runtime_state.get("mqttLastAcceptedTimestamp")
                if (
                    timestamp_value is not None
                    and last_accepted is not None
                    and timestamp_value < int(last_accepted)
                ):
                    runtime_state["mqttIgnoredStateRaw"] = raw_state
                    runtime_state["mqttIgnoredTimestamp"] = timestamp_value
                    return

                # Navimow currently emits the misspelled transient state
                # "isIdel" around docking. It is not authoritative for the UI
                # and must not overwrite a meaningful state such as returning
                # or docked.
                if raw_state == "isIdel":
                    runtime_state["mqttIgnoredStateRaw"] = raw_state
                    runtime_state["mqttIgnoredTimestamp"] = timestamp_value
                    return

                state_map = {
                    "isRunning": "mowing",
                    "isPaused": "paused",
                    "isDocking": "returning",
                    "isDocked": "docked",
                }
                normalized_state = state_map.get(raw_state, raw_state)

                runtime_state["mqttStatusRaw"] = raw_state
                runtime_state["mqttStatus"] = normalized_state
                runtime_state["mqttBattery"] = payload_data.get("battery")
                runtime_state["mqttTimestamp"] = raw_timestamp
                if timestamp_value is not None:
                    runtime_state["mqttLastAcceptedTimestamp"] = timestamp_value

                emit(
                    "status",
                    deviceId=str(payload_data.get("device_id") or device_id),
                    data={
                        "device_id": str(payload_data.get("device_id") or device_id),
                        "status": normalized_state,
                        "status_raw": raw_state,
                        "battery": payload_data.get("battery"),
                        "error_code": payload_data.get("error_code") or "none",
                        "timestamp": raw_timestamp,
                    },
                )
            except Exception as error:
                emit(
                    "error",
                    stage="mqttMessage",
                    deviceId=device_id,
                    message=redact(str(error), secrets),
                )

        def on_disconnect(
            client: Any,
            userdata: Any,
            disconnect_flags: Any,
            reason_code: Any,
            properties: Any,
        ) -> None:
            rc_value = getattr(reason_code, "value", reason_code)
            if int(rc_value) != 0:
                emit("mqttState", deviceId=device_id, state="disconnected", message=f"rc={rc_value}")

        mqtt_client.on_connect = on_connect
        mqtt_client.on_subscribe = on_subscribe
        mqtt_client.on_message = on_message
        mqtt_client.on_disconnect = on_disconnect

        emit("mqttState", deviceId=device_id, state="connecting", broker=f"{host}:{port}", path=path)
        mqtt_client.reconnect_delay_set(min_delay=1, max_delay=30)
        mqtt_client.connect_async(host, port=port, keepalive=60)
        mqtt_client.loop_start()
        try:
            connected_task = asyncio.create_task(connected.wait())
            failed_task = asyncio.create_task(failed.wait())
            done, pending = await asyncio.wait(
                {connected_task, failed_task}, timeout=20.0,
                return_when=asyncio.FIRST_COMPLETED,
            )
            for pending_task in pending:
                pending_task.cancel()
            if failed.is_set():
                raise RuntimeError(failure["message"] or "MQTT-Verbindung fehlgeschlagen")
            if not connected.is_set():
                raise TimeoutError("MQTT connection timeout")
            while True:
                await asyncio.sleep(3600)
        finally:
            try:
                mqtt_client.disconnect()
            except Exception:
                pass
            mqtt_client.loop_stop()

    private_location_task = None
    heartbeat_task = None
    command_input_task = None
    mqtt_task = None

    try:
        emit("softwareVersions", deviceId=device_id, versions=component_versions)

        private_location_task = asyncio.create_task(
            _private_location_loop(configuration, device_id, secrets, runtime_state)
        )
        heartbeat_task = asyncio.create_task(heartbeat_loop())
        command_input_task = asyncio.create_task(command_input_loop())

        mqtt_available = False
        if mqtt_enabled and access_token and mqtt_host and mqtt_url and mqtt_user and mqtt_password:
            mqtt_task = asyncio.create_task(mqtt_loop())
            try:
                await asyncio.sleep(3.2)
                if mqtt_task.done():
                    await mqtt_task
                mqtt_available = True
            except Exception as error:
                emit("mqttState", deviceId=device_id, state="error",
                     message=redact(str(error), secrets))
                log("Navimow: MQTT nicht verfügbar; private Cloud-Verbindung läuft weiter:")
                traceback.print_exc(file=sys.stderr)
                mqtt_task = None
        else:
            emit("mqttState", deviceId=device_id, state="disabled",
                 message="missing MQTT credentials/accessToken or disabled")

        emit(
            "running",
            deviceId=device_id,
            mode="hybrid" if mqtt_available else "private-only",
            mqttAvailable=mqtt_available,
            mqttEnabled=mqtt_enabled,
            projectVersion=PROJECT_VERSION,
            bridgeVersion=BRIDGE_VERSION,
        )

        done, _ = await asyncio.wait(
            {private_location_task, heartbeat_task, command_input_task},
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in done:
            await task

    except asyncio.CancelledError:
        emit("stopped", deviceId=device_id, reason="cancelled")
        raise

    finally:
        for task in (
            private_location_task,
            heartbeat_task,
            command_input_task,
            mqtt_task,
        ):
            if task is None:
                continue
            if not task.done():
                task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            except Exception:
                pass

        emit("disconnected", deviceId=device_id)


def parse_arguments() -> argparse.Namespace:
    """Parse command-line arguments."""

    parser = argparse.ArgumentParser(
        description="Navimow private-cloud bridge for FHEM"
    )

    parser.add_argument(
        "--check",
        action="store_true",
        help="check imports and exit",
    )

    return parser.parse_args()


def main() -> int:
    """Program entry point."""

    arguments = parse_arguments()

    if arguments.check:
        emit(
            "check",
            result="ok",
            python=sys.version.split()[0],
        )
        return 0

    configuration: dict[str, Any] = {}

    try:
        configuration = read_configuration()
        asyncio.run(run_bridge(configuration))
        return 0

    except KeyboardInterrupt:
        emit(
            "stopped",
            reason="keyboardInterrupt",
        )
        return 0

    except Exception as error:
        secrets = [
            str(configuration.get("privateEmail", "")),
            str(configuration.get("privatePassword", "")),
        ]

        safe_message = redact(str(error), secrets)

        emit(
            "fatal",
            message=safe_message,
        )

        log("Navimow: Bridge beendet:")
        traceback.print_exc(file=sys.stderr)

        return 1


if __name__ == "__main__":
    raise SystemExit(main())
