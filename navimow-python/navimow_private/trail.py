#!/usr/bin/env python3
# -*- coding: utf-8 -*-

##############################################################################
#
# Navimow Digital Twin
#
# Module      : trail.py
# Version     : 1.0.0
# Project     : 7.7.4
# Created     : 2026-08-05
# Last Change : 2026-08-05
#
# Description :
# Bounded, filtered trail storage for Navimow world coordinates.
#
# Public API  :
# TrailPoint
# TrailEngine
# module_info()
#
# Change History
# --------------
#
# 1.0.0  2026-08-05
#   Added:
#     - Ring buffer
#     - Distance/time filtering
#     - Immutable TrailPoint entries
#     - Distance and duration statistics
#
##############################################################################

from __future__ import annotations

from collections import deque
from dataclasses import asdict, dataclass
from math import hypot
from typing import Any

MODULE_NAME = "trail"
MODULE_VERSION = "1.0.0"
PROJECT_VERSION = "7.7.4"


def module_info() -> dict[str, str]:
    return {
        "module": MODULE_NAME,
        "version": MODULE_VERSION,
        "project": PROJECT_VERSION,
        "description": "Filtered position trail for the Navimow Digital Twin",
    }


@dataclass(slots=True, frozen=True)
class TrailPoint:
    sequence: int
    timestamp: float
    x: float
    y: float
    distance_from_previous: float

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class TrailEngine:
    def __init__(
        self,
        *,
        max_points: int = 250,
        minimum_distance: float = 0.05,
        minimum_time: float = 2.0,
    ) -> None:
        max_points = int(max_points)
        minimum_distance = float(minimum_distance)
        minimum_time = float(minimum_time)

        if max_points < 2:
            raise ValueError("max_points must be at least 2")
        if minimum_distance < 0:
            raise ValueError("minimum_distance must not be negative")
        if minimum_time < 0:
            raise ValueError("minimum_time must not be negative")

        self._points: deque[TrailPoint] = deque(maxlen=max_points)
        self._sequence = 0
        self._total_distance = 0.0
        self.minimum_distance = minimum_distance
        self.minimum_time = minimum_time

    @property
    def size(self) -> int:
        return len(self._points)

    @property
    def max_points(self) -> int:
        return int(self._points.maxlen or 0)

    @property
    def sequence(self) -> int:
        return self._sequence

    @property
    def total_distance(self) -> float:
        return self._total_distance

    @property
    def duration(self) -> float:
        if len(self._points) < 2:
            return 0.0
        return max(0.0, self._points[-1].timestamp - self._points[0].timestamp)

    def append(
        self,
        x: float,
        y: float,
        timestamp: float,
        *,
        force: bool = False,
    ) -> TrailPoint | None:
        x = float(x)
        y = float(y)
        timestamp = float(timestamp)

        latest = self.latest()
        distance = 0.0
        elapsed = 0.0

        if latest is not None:
            distance = hypot(x - latest.x, y - latest.y)
            elapsed = timestamp - latest.timestamp

            if elapsed < 0 and not force:
                return None

            if (
                not force
                and distance < self.minimum_distance
                and elapsed < self.minimum_time
            ):
                return None

        self._sequence += 1
        point = TrailPoint(
            sequence=self._sequence,
            timestamp=timestamp,
            x=x,
            y=y,
            distance_from_previous=distance,
        )
        self._points.append(point)
        self._total_distance += distance
        return point

    def latest(self) -> TrailPoint | None:
        return self._points[-1] if self._points else None

    def first(self) -> TrailPoint | None:
        return self._points[0] if self._points else None

    def points(self) -> tuple[TrailPoint, ...]:
        return tuple(self._points)

    def last(self, count: int = 20) -> tuple[TrailPoint, ...]:
        count = max(0, int(count))
        if count == 0:
            return ()
        return tuple(list(self._points)[-count:])

    def between(self, start: float, end: float) -> tuple[TrailPoint, ...]:
        start = float(start)
        end = float(end)
        if end < start:
            start, end = end, start
        return tuple(
            point for point in self._points
            if start <= point.timestamp <= end
        )

    def clear(self) -> None:
        self._points.clear()
        self._sequence = 0
        self._total_distance = 0.0

    def snapshot(self, count: int | None = None) -> list[dict[str, Any]]:
        points = list(self._points)
        if count is not None:
            count = max(0, int(count))
            points = points[-count:] if count else []
        return [point.as_dict() for point in points]

    def statistics(self) -> dict[str, Any]:
        return {
            "size": self.size,
            "maxPoints": self.max_points,
            "sequence": self.sequence,
            "totalDistance": self.total_distance,
            "duration": self.duration,
            "minimumDistance": self.minimum_distance,
            "minimumTime": self.minimum_time,
        }
