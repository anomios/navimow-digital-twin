#!/usr/bin/env python3
# -*- coding: utf-8 -*-

##############################################################################
#
# Navimow Digital Twin
#
# Module      : renderer_svg.py
# Version     : 1.8.0
# Project     : 7.8.43
# Created     : 2026-08-03
# Last Change : 2026-08-08
#
# Description :
# Stateless layered SVG renderer for RendererFrame objects.
#
# Public API  :
# RendererStyle
# SVGRenderer
# module_info()
#
# Change History
# --------------
#
# 1.8.0  2026-08-11
# Changed:
# - Charging station is rendered as a prominent black circle with white bolt
# - Navigation connection remains visible behind/beside the station symbol
#
# 1.7.0  2026-08-11
# Changed:
# - Zone labels rendered above map-detail layers with a contrast halo
# - Legacy Motion/Area/Zone/Speed overlay removed from normal rendering
#
# 1.6.0  2026-08-08
#   Added:
#     - Optional mower-free base-map rendering
#     - Public mower_screen_state() for browser overlays
#   Changed:
#     - Viewport creation centralized for identical map/overlay coordinates
#
# 1.5.0  2026-08-08
#   Changed:
#     - Mower is always emitted as one transformable SVG group
#     - Custom mower icon uses local coordinates inside that group
#   Added:
#     - data-x/data-y/data-angle attributes for browser interpolation
#
# 1.4.0  2026-08-08
#   Added:
#     - No-go zone layer
#     - No-vision fence layer
#     - Guaranteed in-polygon zone labels
#   Changed:
#     - Custom mower icons are intended to be embedded data URIs
#
# 1.2.0  2026-08-06
#   Added:
#     - Trail layer and configurable trail styling
#     - Viewport zoom and pan
#     - Configurable heading offset
#   Fixed:
#     - Mower symbol axis rotated 90 degrees to the right
#
# 1.1.0  2026-08-05
#   Added:
#     - Dedicated Viewport integration
#     - RendererStyle configuration
#     - Layered SVG output
#     - Stylized mower and dock symbols
#     - Improved zone filling and tunnel presentation
#
# 1.0.0  2026-08-03
#   Added:
#     - Initial SVG renderer
#
##############################################################################

"""Layered SVG renderer for the Navimow Digital Twin."""
from __future__ import annotations

from dataclasses import dataclass
from html import escape
import math
from typing import Iterable

from navimow_private.renderer_api import (
    Point2D,
    RendererArea,
    RendererDock,
    RendererFrame,
    RendererMower,
    RendererTunnel,
    RendererZone,
)
from navimow_private.viewport import Viewport

MODULE_NAME = "renderer_svg"
MODULE_VERSION = "1.4.0"
PROJECT_VERSION = "7.8.43"


def module_info() -> dict[str, str]:
    return {
        "module": MODULE_NAME,
        "version": MODULE_VERSION,
        "project": PROJECT_VERSION,
        "description": "Layered SVG renderer for RendererFrame objects",
    }


@dataclass(slots=True, frozen=True)
class RendererStyle:
    background: str = "#ffffff"
    zone_fill: str = "#dfeee0"
    zone_fill_opacity: float = 0.62
    zone_stroke: str = "#477a4b"
    zone_stroke_width: float = 2.0
    tunnel_stroke: str = "#666666"
    tunnel_width: float = 5.0
    no_go_fill: str = "#8b8b8b"
    no_go_stroke: str = "#3f3f3f"
    no_go_opacity: float = 0.72
    vision_off_fill: str = "#d0b35a"
    vision_off_stroke: str = "#8c7426"
    vision_off_opacity: float = 0.28
    trail_stroke: str = "#2f7d32"
    trail_width: float = 1.0
    trail_opacity: float = 0.78
    dock_fill: str = "#d9d9d9"
    dock_stroke: str = "#333333"
    mower_fill: str = "#70b85a"
    mower_stroke: str = "#1f4d24"
    heading_stroke: str = "#1f4d24"
    text_fill: str = "#222222"
    mower_width: float = 18.0
    mower_height: float = 24.0
    heading_length: float = 34.0
    dock_width: float = 22.0
    dock_height: float = 14.0
    font_size: float = 14.0
    heading_offset_degrees: float = 90.0
    mower_icon_href: str = ""


class SVGRenderer:
    def __init__(
        self,
        *,
        width: int = 900,
        height: int = 650,
        padding: float = 32.0,
        show_labels: bool = True,
        style: RendererStyle | None = None,
        zoom: float = 1.0,
        pan_x: float = 0.0,
        pan_y: float = 0.0,
    ) -> None:
        self.width = int(width)
        self.height = int(height)
        self.padding = float(padding)
        self.show_labels = bool(show_labels)
        self.style = style or RendererStyle()
        self.zoom = float(zoom)
        self.pan_x = float(pan_x)
        self.pan_y = float(pan_y)

    def _viewport(self, frame: RendererFrame) -> Viewport:
        return Viewport.from_points(
            self._all_points(frame),
            width=self.width,
            height=self.height,
            padding=self.padding,
            zoom=self.zoom,
            pan_x=self.pan_x,
            pan_y=self.pan_y,
        )

    def mower_screen_state(self, frame: RendererFrame) -> dict[str, float] | None:
        if frame.mower.position is None:
            return None
        viewport = self._viewport(frame)
        x, y = viewport.world_to_screen(frame.mower.position)
        angle = (
            float(frame.mower.heading_degrees or 0.0)
            + self.style.heading_offset_degrees
        )
        return {
            "x": float(x),
            "y": float(y),
            "angle": float(angle),
            "width": float(self.style.mower_width),
            "height": float(self.style.mower_height),
            "canvasWidth": float(self.width),
            "canvasHeight": float(self.height),
        }

    def render(
        self,
        frame: RendererFrame,
        *,
        include_mower: bool = True,
    ) -> str:
        viewport = self._viewport(frame)

        parts = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            (
                f'<svg xmlns="http://www.w3.org/2000/svg" '
                f'width="{self.width}" height="{self.height}" '
                f'viewBox="0 0 {self.width} {self.height}" '
                f'preserveAspectRatio="xMidYMid meet" '
                f'role="img" aria-label="Navimow Digital Twin">'
            ),
            self._defs(),
            self._background(),
            '<g id="zones">',
            *self._draw_zones(frame.zones, viewport),
            "</g>",
            '<g id="no-go-areas">',
            *self._draw_areas(
                frame.no_go_areas,
                viewport,
                fill=self.style.no_go_fill,
                stroke=self.style.no_go_stroke,
                opacity=self.style.no_go_opacity,
                css_class="no-go-area",
            ),
            "</g>",
            '<g id="vision-off-areas">',
            *self._draw_areas(
                frame.vision_off_areas,
                viewport,
                fill=self.style.vision_off_fill,
                stroke=self.style.vision_off_stroke,
                opacity=self.style.vision_off_opacity,
                css_class="vision-off-area",
                dashed=True,
            ),
            "</g>",
            '<g id="tunnels">',
            *self._draw_tunnels(frame.tunnels, viewport),
            "</g>",
            '<g id="trail">',
            *self._draw_trail(frame.trail, viewport),
            "</g>",
            '<g id="docks">',
            *self._draw_docks(frame.docks, viewport),
            "</g>",
            '<g id="zone-labels">',
            *(
                self._draw_zone_labels(frame.zones, viewport)
                if self.show_labels
                else []
            ),
            "</g>",
            '<g id="mower">',
            *(
                self._draw_mower(frame.mower, viewport)
                if include_mower
                else []
            ),
            "</g>",
        ]

        parts.append("</svg>")
        return "\n".join(parts)

    def _defs(self) -> str:
        return (
            "<defs>"
            '<filter id="softShadow" x="-30%" y="-30%" width="160%" height="160%">'
            '<feDropShadow dx="0" dy="1.5" stdDeviation="1.5" flood-opacity="0.25"/>'
            "</filter>"
            "</defs>"
        )

    def _background(self) -> str:
        background = self.style.background.strip().lower()
        if background in ("", "none", "transparent"):
            return '<g id="background"/>'
        return (
            f'<rect id="background" x="0" y="0" '
            f'width="{self.width}" height="{self.height}" '
            f'fill="{escape(self.style.background)}"/>'
        )

    def _all_points(self, frame: RendererFrame) -> Iterable[Point2D]:
        for zone in frame.zones:
            for polygon in zone.polygons:
                yield from polygon
        for area in frame.no_go_areas:
            yield from area.points
        for area in frame.vision_off_areas:
            yield from area.points
        for tunnel in frame.tunnels:
            yield from tunnel.points
        for dock in frame.docks:
            if dock.position is not None:
                yield dock.position
            if dock.navigation_position is not None:
                yield dock.navigation_position
        for segment in frame.trail:
            yield from segment
        if frame.mower.position is not None:
            yield frame.mower.position

    def _draw_zones(
        self,
        zones: tuple[RendererZone, ...],
        viewport: Viewport,
    ) -> list[str]:
        parts: list[str] = []
        for zone in zones:
            for index, polygon in enumerate(zone.polygons):
                coords = " ".join(
                    f"{x:.2f},{y:.2f}"
                    for x, y in (
                        viewport.world_to_screen(point) for point in polygon
                    )
                )
                parts.append(
                    f'<polygon id="zone-{escape(zone.zone_id)}-{index}" '
                    f'points="{coords}" '
                    f'fill="{escape(self.style.zone_fill)}" '
                    f'fill-opacity="{self.style.zone_fill_opacity:.3f}" '
                    f'stroke="{escape(self.style.zone_stroke)}" '
                    f'stroke-width="{self.style.zone_stroke_width:.2f}" '
                    f'stroke-linejoin="round"/>'
                )

        return parts

    def _draw_zone_labels(
        self,
        zones: tuple[RendererZone, ...],
        viewport: Viewport,
    ) -> list[str]:
        parts: list[str] = []
        for zone in zones:
            if not zone.polygons or not zone.polygons[0]:
                continue
            center = self._label_point(zone.polygons[0])
            x, y = viewport.world_to_screen(center)
            label = escape(zone.name or f"Zone {zone.zone_id}")
            parts.append(
                f'<text x="{x:.2f}" y="{y:.2f}" '
                f'transform="rotate(-30 {x:.2f} {y:.2f})" '
                f'text-anchor="middle" '
                f'font-size="{self.style.font_size:.1f}" '
                f'font-family="sans-serif" font-weight="600" '
                f'fill="{escape(self.style.text_fill)}" '
                f'stroke="#ffffff" stroke-opacity="0.94" '
                f'stroke-width="4.0" stroke-linejoin="round" '
                f'paint-order="stroke fill">{label}</text>'
            )
        return parts

    @staticmethod
    def _point_in_polygon(point: Point2D, polygon: tuple[Point2D, ...]) -> bool:
        inside = False
        j = len(polygon) - 1
        for i, pi in enumerate(polygon):
            pj = polygon[j]
            intersects = (
                (pi.y > point.y) != (pj.y > point.y)
                and point.x
                < (pj.x - pi.x) * (point.y - pi.y)
                / ((pj.y - pi.y) or 1e-12)
                + pi.x
            )
            if intersects:
                inside = not inside
            j = i
        return inside

    @staticmethod
    def _distance_to_segment(point: Point2D, a: Point2D, b: Point2D) -> float:
        dx = b.x - a.x
        dy = b.y - a.y
        if dx == 0 and dy == 0:
            return math.hypot(point.x - a.x, point.y - a.y)
        t = ((point.x - a.x) * dx + (point.y - a.y) * dy) / (dx * dx + dy * dy)
        t = max(0.0, min(1.0, t))
        px = a.x + t * dx
        py = a.y + t * dy
        return math.hypot(point.x - px, point.y - py)

    def _label_point(self, polygon: tuple[Point2D, ...]) -> Point2D:
        average = Point2D(
            sum(p.x for p in polygon) / len(polygon),
            sum(p.y for p in polygon) / len(polygon),
        )
        if self._point_in_polygon(average, polygon):
            return average

        min_x = min(p.x for p in polygon)
        max_x = max(p.x for p in polygon)
        min_y = min(p.y for p in polygon)
        max_y = max(p.y for p in polygon)

        best = polygon[0]
        best_distance = -1.0
        steps = 20
        for ix in range(steps + 1):
            for iy in range(steps + 1):
                candidate = Point2D(
                    min_x + (max_x - min_x) * ix / steps,
                    min_y + (max_y - min_y) * iy / steps,
                )
                if not self._point_in_polygon(candidate, polygon):
                    continue
                distance = min(
                    self._distance_to_segment(
                        candidate,
                        polygon[index],
                        polygon[(index + 1) % len(polygon)],
                    )
                    for index in range(len(polygon))
                )
                if distance > best_distance:
                    best = candidate
                    best_distance = distance
        return best

    def _draw_areas(
        self,
        areas: tuple[RendererArea, ...],
        viewport: Viewport,
        *,
        fill: str,
        stroke: str,
        opacity: float,
        css_class: str,
        dashed: bool = False,
    ) -> list[str]:
        parts: list[str] = []
        for area in areas:
            coords = " ".join(
                f"{x:.2f},{y:.2f}"
                for x, y in (
                    viewport.world_to_screen(point) for point in area.points
                )
            )
            dash = ' stroke-dasharray="8 6"' if dashed else ""
            parts.append(
                f'<polygon class="{css_class}" points="{coords}" '
                f'fill="{escape(fill)}" fill-opacity="{opacity:.3f}" '
                f'stroke="{escape(stroke)}" stroke-width="2"{dash}/>'
            )
        return parts

    def _draw_tunnels(
        self,
        tunnels: tuple[RendererTunnel, ...],
        viewport: Viewport,
    ) -> list[str]:
        parts: list[str] = []
        for tunnel in tunnels:
            coords = " ".join(
                f"{x:.2f},{y:.2f}"
                for x, y in (
                    viewport.world_to_screen(point) for point in tunnel.points
                )
            )
            parts.append(
                f'<polyline id="tunnel-{escape(tunnel.tunnel_id)}" '
                f'points="{coords}" fill="none" '
                f'stroke="{escape(self.style.tunnel_stroke)}" '
                f'stroke-width="{self.style.tunnel_width:.2f}" '
                f'stroke-linecap="round" stroke-linejoin="round" '
                f'stroke-dasharray="10 7"/>'
            )
        return parts

    def _draw_trail(
        self,
        trail: tuple[tuple[Point2D, ...], ...],
        viewport: Viewport,
    ) -> list[str]:
        parts: list[str] = []
        for segment in trail:
            if len(segment) < 2:
                continue
            coords = " ".join(
                f"{x:.2f},{y:.2f}"
                for x, y in (
                    viewport.world_to_screen(point) for point in segment
                )
            )
            parts.append(
                f'<polyline points="{coords}" fill="none" '
                f'stroke="{escape(self.style.trail_stroke)}" '
                f'stroke-width="{self.style.trail_width:.2f}" '
                f'stroke-opacity="{self.style.trail_opacity:.3f}" '
                f'stroke-linecap="round" stroke-linejoin="round"/>'
            )
        return parts

    def _draw_docks(
        self,
        docks: tuple[RendererDock, ...],
        viewport: Viewport,
    ) -> list[str]:
        parts: list[str] = []
        for dock in docks:
            if dock.position is None:
                continue

            x, y = viewport.world_to_screen(dock.position)
            w = self.style.dock_width
            h = self.style.dock_height
            radius = max(w, h) * 0.68
            bolt = [
                (-0.10 * radius, -0.62 * radius),
                ( 0.32 * radius, -0.62 * radius),
                ( 0.06 * radius, -0.10 * radius),
                ( 0.42 * radius, -0.10 * radius),
                (-0.28 * radius,  0.68 * radius),
                (-0.04 * radius,  0.12 * radius),
                (-0.38 * radius,  0.12 * radius),
            ]
            bolt_points = " ".join(
                f"{px:.2f},{py:.2f}" for px, py in bolt
            )

            parts.append(
                f'<g id="dock-{escape(dock.dock_id)}" '
                f'transform="translate({x:.2f} {y:.2f})" '
                f'filter="url(#softShadow)">'
                f'<circle cx="0" cy="0" r="{radius:.2f}" '
                f'fill="#000000" stroke="#000000" stroke-width="2"/>'
                f'<polygon points="{bolt_points}" '
                f'fill="#ffffff" stroke="#ffffff" '
                f'stroke-width="1.0" stroke-linejoin="round"/>'
                "</g>"
            )

            if dock.navigation_position is not None:
                nx, ny = viewport.world_to_screen(dock.navigation_position)
                parts.append(
                    f'<line x1="{x:.2f}" y1="{y:.2f}" '
                    f'x2="{nx:.2f}" y2="{ny:.2f}" '
                    f'stroke="{escape(self.style.dock_stroke)}" '
                    f'stroke-width="1.5" stroke-dasharray="4 4"/>'
                )
        return parts

    def _draw_mower(
        self,
        mower: RendererMower,
        viewport: Viewport,
    ) -> list[str]:
        if mower.position is None:
            return []

        x, y = viewport.world_to_screen(mower.position)
        angle = (
            float(mower.heading_degrees or 0.0)
            + self.style.heading_offset_degrees
        )
        w = self.style.mower_width
        h = self.style.mower_height

        group_open = (
            f'<g id="mower-symbol" '
            f'data-x="{x:.4f}" data-y="{y:.4f}" '
            f'data-angle="{angle:.4f}" '
            f'transform="translate({x:.4f} {y:.4f}) rotate({angle:.4f})" '
            f'filter="url(#softShadow)">'
        )

        if self.style.mower_icon_href.strip():
            href = escape(self.style.mower_icon_href.strip(), quote=True)
            return [
                (
                    group_open
                    + f'<image href="{href}" '
                    f'x="{-w/2:.2f}" y="{-h/2:.2f}" '
                    f'width="{w:.2f}" height="{h:.2f}" '
                    f'preserveAspectRatio="xMidYMid meet"/>'
                    + "</g>"
                )
            ]

        return [
            (
                group_open
                + f'<rect x="{-w/2:.2f}" y="{-h/2:.2f}" '
                f'width="{w:.2f}" height="{h:.2f}" rx="7" '
                f'fill="{escape(self.style.mower_fill)}" '
                f'stroke="{escape(self.style.mower_stroke)}" '
                f'stroke-width="2.5"/>'
                f'<path d="M {-w/2+4:.2f} {-h/2+6:.2f} '
                f'L 0 {-h/2+1:.2f} L {w/2-4:.2f} {-h/2+6:.2f}" '
                f'fill="none" stroke="{escape(self.style.mower_stroke)}" '
                f'stroke-width="2"/>'
                + "</g>"
            )
        ]

    def _draw_overlay(self, frame: RendererFrame) -> list[str]:
        mower = frame.mower
        lines = [
            f"Motion: {mower.motion_detail}",
            f"Area: {mower.location_area}",
            f"Zone: {mower.zone_name or '-'}",
            f"Speed: {mower.speed_mps:.3f} m/s",
        ]

        box_width = 215
        box_height = 22 + 20 * len(lines)

        parts = [
            '<g id="overlay">',
            (
                f'<rect x="10" y="10" width="{box_width}" '
                f'height="{box_height}" rx="8" '
                f'fill="#ffffff" fill-opacity="0.88" '
                f'stroke="#bbbbbb" stroke-width="1"/>'
            ),
        ]

        y = 32.0
        for line in lines:
            parts.append(
                f'<text x="22" y="{y:.2f}" '
                f'font-size="{self.style.font_size:.1f}" '
                f'font-family="sans-serif" '
                f'fill="{escape(self.style.text_fill)}">{escape(line)}</text>'
            )
            y += 20.0

        parts.append("</g>")
        return parts
