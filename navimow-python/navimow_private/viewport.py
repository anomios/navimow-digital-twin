#!/usr/bin/env python3
# -*- coding: utf-8 -*-

##############################################################################
#
# Navimow Digital Twin
#
# Module      : viewport.py
# Version     : 1.2.0
# Project     : 7.7.6
# Created     : 2026-08-05
# Last Change : 2026-08-06
#
# Description :
# World-to-screen transformation with automatic bounds, centering,
# aspect-ratio preservation and configurable padding.
#
# Public API  :
# Viewport
# module_info()
#
# Change History
# --------------
#
# 1.1.0  2026-08-06
#   Added:
#     - Configurable zoom
#     - Pan in world coordinates
#
# 1.0.0  2026-08-05
#   Added:
#     - Automatic world bounds
#     - Aspect-ratio preserving scaling
#     - Centered viewport transform
#     - Defensive handling of empty and degenerate geometry
#
##############################################################################

"""Viewport transformation for Navimow renderers."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from navimow_private.renderer_api import Point2D

MODULE_NAME = "viewport"
MODULE_VERSION = "1.2.0"
PROJECT_VERSION = "7.7.6"


def module_info() -> dict[str, str]:
    return {
        "module": MODULE_NAME,
        "version": MODULE_VERSION,
        "project": PROJECT_VERSION,
        "description": "World-to-screen transformation for Navimow renderers",
    }


@dataclass(slots=True, frozen=True)
class Viewport:
    width: int
    height: int
    padding: float
    min_x: float
    max_x: float
    min_y: float
    max_y: float
    scale: float
    offset_x: float
    offset_y: float

    @classmethod
    def from_points(
        cls,
        points: Iterable[Point2D],
        *,
        width: int = 900,
        height: int = 650,
        padding: float = 32.0,
        zoom: float = 1.0,
        pan_x: float = 0.0,
        pan_y: float = 0.0,
    ) -> "Viewport":
        width = int(width)
        height = int(height)
        padding = float(padding)
        zoom = float(zoom)
        pan_x = float(pan_x)
        pan_y = float(pan_y)

        if width < 100 or height < 100:
            raise ValueError("width and height must be at least 100")
        if padding < 0:
            raise ValueError("padding must not be negative")
        if padding * 2 >= width or padding * 2 >= height:
            raise ValueError("padding leaves no usable viewport area")
        if zoom <= 0:
            raise ValueError("zoom must be greater than zero")

        values = list(points)
        if not values:
            values = [Point2D(0.0, 0.0), Point2D(1.0, 1.0)]

        min_x = min(point.x for point in values)
        max_x = max(point.x for point in values)
        min_y = min(point.y for point in values)
        max_y = max(point.y for point in values)

        if max_x == min_x:
            min_x -= 0.5
            max_x += 0.5
        if max_y == min_y:
            min_y -= 0.5
            max_y += 0.5

        span_x = max_x - min_x
        span_y = max_y - min_y
        usable_width = width - 2.0 * padding
        usable_height = height - 2.0 * padding

        scale = min(usable_width / span_x, usable_height / span_y) * zoom

        drawn_width = span_x * scale
        drawn_height = span_y * scale
        offset_x = padding + (usable_width - drawn_width) / 2.0 + pan_x
        offset_y = padding + (usable_height - drawn_height) / 2.0 + pan_y

        return cls(
            width=width,
            height=height,
            padding=padding,
            min_x=min_x,
            max_x=max_x,
            min_y=min_y,
            max_y=max_y,
            scale=scale,
            offset_x=offset_x,
            offset_y=offset_y,
        )

    def world_to_screen(self, point: Point2D) -> tuple[float, float]:
        x = self.offset_x + (point.x - self.min_x) * self.scale
        y = self.offset_y + (self.max_y - point.y) * self.scale
        return x, y

    def screen_to_world(self, x: float, y: float) -> Point2D:
        world_x = self.min_x + (float(x) - self.offset_x) / self.scale
        world_y = self.max_y - (float(y) - self.offset_y) / self.scale
        return Point2D(world_x, world_y)
