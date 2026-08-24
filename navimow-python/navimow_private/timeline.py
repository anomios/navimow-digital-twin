"""Immutable in-memory timeline for the Navimow digital twin."""
from __future__ import annotations

from collections import deque
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Iterable

MODULE_NAME = "timeline"
MODULE_VERSION = "1.0.0"
PROJECT_VERSION = "7.5.0"


def module_info() -> dict[str, str]:
    return {
        "module": MODULE_NAME,
        "version": MODULE_VERSION,
        "project": PROJECT_VERSION,
    }


@dataclass(slots=True, frozen=True)
class TimelineEntry:
    sequence: int
    timestamp: float
    snapshot: dict[str, Any]
    events: tuple[dict[str, Any], ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "sequence": self.sequence,
            "timestamp": self.timestamp,
            "snapshot": deepcopy(self.snapshot),
            "events": [deepcopy(event) for event in self.events],
        }


class TimelineEngine:
    """Bounded chronological store for snapshots and semantic events."""

    def __init__(self, max_entries: int = 5000) -> None:
        max_entries = int(max_entries)
        if max_entries < 1:
            raise ValueError("max_entries must be at least 1")
        self._entries: deque[TimelineEntry] = deque(maxlen=max_entries)
        self._sequence = 0

    @property
    def size(self) -> int:
        return len(self._entries)

    @property
    def max_entries(self) -> int:
        return int(self._entries.maxlen or 0)

    @property
    def sequence(self) -> int:
        return self._sequence

    def append(
        self,
        timestamp: float,
        snapshot: dict[str, Any],
        events: Iterable[Any] = (),
    ) -> TimelineEntry:
        self._sequence += 1

        frozen_events: list[dict[str, Any]] = []
        for event in events:
            if hasattr(event, "as_dict"):
                frozen_events.append(deepcopy(event.as_dict()))
            elif isinstance(event, dict):
                frozen_events.append(deepcopy(event))
            else:
                raise TypeError(
                    "timeline events must be dictionaries or provide as_dict()"
                )

        entry = TimelineEntry(
            sequence=self._sequence,
            timestamp=float(timestamp),
            snapshot=deepcopy(snapshot),
            events=tuple(frozen_events),
        )
        self._entries.append(entry)
        return entry

    def latest(self) -> TimelineEntry | None:
        return self._entries[-1] if self._entries else None

    def last(self, count: int = 10) -> list[TimelineEntry]:
        count = max(0, int(count))
        if count == 0:
            return []
        return list(self._entries)[-count:]

    def between(self, start: float, end: float) -> list[TimelineEntry]:
        start = float(start)
        end = float(end)
        if end < start:
            start, end = end, start
        return [
            entry
            for entry in self._entries
            if start <= entry.timestamp <= end
        ]

    def clear(self) -> None:
        self._entries.clear()
        self._sequence = 0

    def snapshot(self, count: int | None = None) -> list[dict[str, Any]]:
        entries = list(self._entries)
        if count is not None:
            count = max(0, int(count))
            entries = entries[-count:] if count else []
        return [entry.as_dict() for entry in entries]
