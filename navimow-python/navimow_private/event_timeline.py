"""Semantic event timeline for the Navimow digital twin."""
from __future__ import annotations

from collections import deque
from copy import deepcopy
from dataclasses import asdict, dataclass
from typing import Any, Iterable

MODULE_NAME = "event_timeline"
MODULE_VERSION = "1.0.0"
PROJECT_VERSION = "7.6.2"


def module_info() -> dict[str, str]:
    return {
        "module": MODULE_NAME,
        "version": MODULE_VERSION,
        "project": PROJECT_VERSION,
        "description": "Semantic event log for the Navimow digital twin",
    }


@dataclass(slots=True, frozen=True)
class EventTimelineEntry:
    sequence: int
    timestamp: float
    name: str
    severity: str
    payload: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["payload"] = deepcopy(self.payload)
        return result


class EventTimelineEngine:
    DEFAULT_SEVERITY = "info"

    def __init__(self, max_entries: int = 1000) -> None:
        max_entries = int(max_entries)
        if max_entries < 1:
            raise ValueError("max_entries must be at least 1")
        self._entries: deque[EventTimelineEntry] = deque(maxlen=max_entries)
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

    def append(self, timestamp: float, events: Iterable[Any]) -> list[EventTimelineEntry]:
        created: list[EventTimelineEntry] = []

        for event in events:
            if hasattr(event, "as_dict"):
                raw = event.as_dict()
            elif isinstance(event, dict):
                raw = deepcopy(event)
            else:
                raise TypeError("events must be dictionaries or provide as_dict()")

            if not isinstance(raw, dict):
                raise TypeError("event as_dict() must return a dictionary")

            name = str(raw.get("name") or "").strip()
            if not name:
                raise ValueError("event name must not be empty")

            event_timestamp = raw.get("timestamp", timestamp)
            data = raw.get("data")
            payload_value = raw.get("payload")

            severity = self.DEFAULT_SEVERITY
            if isinstance(data, dict) and data.get("severity"):
                severity = str(data["severity"])
            elif raw.get("severity"):
                severity = str(raw["severity"])

            if isinstance(data, dict):
                payload = deepcopy(data)
            elif isinstance(payload_value, dict):
                payload = deepcopy(payload_value)
            else:
                payload = {}

            payload.pop("severity", None)

            self._sequence += 1
            entry = EventTimelineEntry(
                sequence=self._sequence,
                timestamp=float(event_timestamp),
                name=name,
                severity=severity,
                payload=payload,
            )
            self._entries.append(entry)
            created.append(entry)

        return created

    def latest(self) -> EventTimelineEntry | None:
        return self._entries[-1] if self._entries else None

    def last(self, count: int = 20) -> list[EventTimelineEntry]:
        count = max(0, int(count))
        if count == 0:
            return []
        return list(self._entries)[-count:]

    def between(self, start: float, end: float) -> list[EventTimelineEntry]:
        start = float(start)
        end = float(end)
        if end < start:
            start, end = end, start
        return [entry for entry in self._entries if start <= entry.timestamp <= end]

    def clear(self) -> None:
        self._entries.clear()
        self._sequence = 0

    def snapshot(self, count: int | None = None) -> list[dict[str, Any]]:
        entries = list(self._entries)
        if count is not None:
            count = max(0, int(count))
            entries = entries[-count:] if count else []
        return [entry.as_dict() for entry in entries]
