"""In-memory history for Navimow digital-twin snapshots and events."""
from __future__ import annotations

MODULE_NAME = "history"
MODULE_VERSION = "1.0.0"
PROJECT_VERSION = "7.4.0"

from collections import deque
from copy import deepcopy
from dataclasses import dataclass
import time
from typing import Any, Iterable

from .events import NavimowEvent


@dataclass(slots=True, frozen=True)
class HistoryEntry:
    timestamp: float
    state: dict[str, Any]
    events: tuple[dict[str, Any], ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "state": deepcopy(self.state),
            "events": [deepcopy(item) for item in self.events],
        }


class HistoryEngine:
    """Bounded ring buffer used by live mode and later by replay."""

    def __init__(self, max_entries: int = 1000) -> None:
        if max_entries < 1:
            raise ValueError("max_entries must be at least 1")
        self._entries: deque[HistoryEntry] = deque(maxlen=max_entries)

    @property
    def size(self) -> int:
        return len(self._entries)

    @property
    def max_entries(self) -> int:
        return int(self._entries.maxlen or 0)

    def append(
        self,
        state: dict[str, Any],
        events: Iterable[NavimowEvent] = (),
        *,
        observed_at: float | None = None,
    ) -> HistoryEntry:
        timestamp = time.time() if observed_at is None else float(observed_at)
        entry = HistoryEntry(
            timestamp=timestamp,
            state=deepcopy(state),
            events=tuple(event.as_dict() for event in events),
        )
        self._entries.append(entry)
        return entry

    def latest(self) -> HistoryEntry | None:
        return self._entries[-1] if self._entries else None

    def snapshot(self, limit: int | None = None) -> list[dict[str, Any]]:
        entries = list(self._entries)
        if limit is not None:
            entries = entries[-max(0, int(limit)) :]
        return [entry.as_dict() for entry in entries]
