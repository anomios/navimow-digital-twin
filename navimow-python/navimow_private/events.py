"""Event detection for the Navimow digital twin."""
from __future__ import annotations

MODULE_NAME = "events"
MODULE_VERSION = "1.0.0"
PROJECT_VERSION = "7.4.0"

from dataclasses import dataclass, field
import time
from typing import Any


@dataclass(slots=True, frozen=True)
class NavimowEvent:
    """A semantic state transition emitted by the digital twin."""

    name: str
    timestamp: float
    data: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "timestamp": self.timestamp,
            "data": dict(self.data),
        }


class EventEngine:
    """Compare consecutive model snapshots and detect meaningful transitions."""

    def __init__(self) -> None:
        self._previous: dict[str, Any] | None = None
        self._sequence = 0

    @property
    def sequence(self) -> int:
        return self._sequence

    def reset(self, snapshot: dict[str, Any] | None = None) -> None:
        """Set a new baseline without producing synthetic startup events."""
        self._previous = snapshot

    @staticmethod
    def _state(snapshot: dict[str, Any]) -> dict[str, Any]:
        motion = snapshot.get("motion") or {}
        geometry = snapshot.get("geometry") or {}
        return {
            "moving": bool(motion.get("moving")),
            "location_area": str(geometry.get("location_area") or "unknown"),
            "zone_id": geometry.get("current_zone_id"),
            "zone_name": str(geometry.get("current_zone_name") or ""),
            "in_tunnel": bool(geometry.get("in_tunnel")),
            "tunnel_id": geometry.get("tunnel_id"),
        }

    def process(
        self,
        snapshot: dict[str, Any],
        *,
        observed_at: float | None = None,
    ) -> list[NavimowEvent]:
        """Return events caused by the transition to *snapshot*.

        The first snapshot only establishes a baseline.
        """
        timestamp = time.time() if observed_at is None else float(observed_at)
        if self._previous is None:
            self._previous = snapshot
            return []

        previous = self._state(self._previous)
        current = self._state(snapshot)
        events: list[NavimowEvent] = []

        def add(name: str, **data: Any) -> None:
            self._sequence += 1
            data["sequence"] = self._sequence
            events.append(NavimowEvent(name=name, timestamp=timestamp, data=data))

        if previous["moving"] != current["moving"]:
            add("motionStarted" if current["moving"] else "motionStopped")

        if previous["location_area"] == "dock" and current["location_area"] != "dock":
            add("dockLeft")
        elif previous["location_area"] != "dock" and current["location_area"] == "dock":
            add("dockReached")

        previous_zone = previous["zone_id"]
        current_zone = current["zone_id"]
        if previous_zone != current_zone:
            if previous_zone not in (None, ""):
                add(
                    "zoneLeft",
                    zoneId=previous_zone,
                    zoneName=previous["zone_name"],
                )
            if current_zone not in (None, ""):
                add(
                    "zoneEntered",
                    zoneId=current_zone,
                    zoneName=current["zone_name"],
                )

        if previous["in_tunnel"] != current["in_tunnel"]:
            if current["in_tunnel"]:
                add("tunnelEntered", tunnelId=current["tunnel_id"])
            else:
                add("tunnelLeft", tunnelId=previous["tunnel_id"])

        self._previous = snapshot
        return events
