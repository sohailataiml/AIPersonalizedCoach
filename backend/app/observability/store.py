"""In-process ring buffer of recent traces.

Deliberately not a database. Traces here are an operator's view of the last few
requests in *this* process; persisting them would mean designing retention,
access control and PII policy for data the assessment does not need. The README
says so plainly rather than implying durability that does not exist.
"""

from __future__ import annotations

from collections import deque
from threading import Lock

from app.domain.trace import RequestTrace

DEFAULT_CAPACITY = 50


class TraceStore:
    """Bounded, newest-first, thread-safe."""

    def __init__(self, capacity: int = DEFAULT_CAPACITY) -> None:
        self._traces: deque[RequestTrace] = deque(maxlen=capacity)
        self._lock = Lock()

    @property
    def capacity(self) -> int:
        return self._traces.maxlen or 0

    def record(self, trace: RequestTrace) -> None:
        with self._lock:
            self._traces.appendleft(trace)

    def recent(self, limit: int | None = None) -> list[RequestTrace]:
        with self._lock:
            traces = list(self._traces)
        return traces[:limit] if limit else traces

    def get(self, request_id: str) -> RequestTrace | None:
        with self._lock:
            return next((t for t in self._traces if t.request_id == request_id), None)

    def clear(self) -> None:
        with self._lock:
            self._traces.clear()

    def __len__(self) -> int:
        return len(self._traces)
