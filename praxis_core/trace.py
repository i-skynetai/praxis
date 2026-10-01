"""Trace sinks: JSONL (the default) and SQLite, and a background queue to put in front
of either so that capture costs the caller microseconds.

The router never lets a sink failure reach the caller, so a sink may raise freely. What a
sink must do is round-trip: ``read()`` yields the same ``TraceEvent`` that ``record()``
was given. Late-bound fields (``outcome``, ``feedback``) are updated by re-recording the
trace; SQLite replaces by ``trace_id``, JSONL appends and the reader keeps the last.

``QueuedTraceSink`` is the "capture is fire-and-forget" rule made concrete: ``record``
enqueues and returns; one daemon thread drains into the inner sink; a full queue drops
and counts, never blocks; an inner failure is counted, never raised. ``flush()`` waits
for the queue to empty, which tests and shutdown need and the request path never does.
"""

from __future__ import annotations

import contextlib
import json
import queue
import sqlite3
import threading
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

from .contracts import TraceEvent
from .ports import TraceSink


class JsonlTraceSink:
    """One JSON object per line, appended. The simplest thing that survives a crash."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._lock = threading.Lock()

    def record(self, trace: TraceEvent) -> None:
        line = trace.to_json()
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")

    def read(self, capability: str | None = None) -> Iterator[TraceEvent]:
        if not self.path.exists():
            return
        latest: dict[str, TraceEvent] = {}
        with self.path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                trace = TraceEvent.from_dict(json.loads(line))
                if capability is None or trace.capability == capability:
                    latest[trace.trace_id] = trace
        yield from latest.values()

    def __repr__(self) -> str:
        return f"JsonlTraceSink({str(self.path)!r})"


class SqliteTraceSink:
    """An envelope row per trace with the full body as JSON, indexed by capability."""

    _SCHEMA = """
        CREATE TABLE IF NOT EXISTS traces (
            trace_id       TEXT PRIMARY KEY,
            capability     TEXT NOT NULL,
            created_at     TEXT NOT NULL,
            stage          TEXT NOT NULL,
            answered_by    TEXT NOT NULL,
            abstain        INTEGER NOT NULL,
            host_partition TEXT,
            body           TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS traces_capability ON traces (capability, created_at);
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        if str(path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        with self._lock:
            self._conn.executescript(self._SCHEMA)
            self._conn.commit()

    def record(self, trace: TraceEvent) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO traces (trace_id, capability, created_at, stage, answered_by, abstain, "
                "host_partition, body) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    trace.trace_id,
                    trace.capability,
                    trace.created_at,
                    trace.stage,
                    trace.answered_by,
                    1 if trace.abstain else 0,
                    trace.host_partition,
                    trace.to_json(),
                ),
            )
            self._conn.commit()

    def read(self, capability: str | None = None) -> Iterator[TraceEvent]:
        query = "SELECT body FROM traces"
        params: tuple[str, ...] = ()
        if capability is not None:
            query += " WHERE capability = ?"
            params = (capability,)
        query += " ORDER BY created_at, rowid"
        with self._lock:
            rows = self._conn.execute(query, params).fetchall()
        for (body,) in rows:
            yield TraceEvent.from_dict(json.loads(body))

    def count(self, capability: str | None = None) -> int:
        with self._lock:
            if capability is None:
                row = self._conn.execute("SELECT COUNT(*) FROM traces").fetchone()
            else:
                row = self._conn.execute("SELECT COUNT(*) FROM traces WHERE capability = ?", (capability,)).fetchone()
        return int(row[0]) if row else 0

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def __enter__(self) -> SqliteTraceSink:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def __repr__(self) -> str:
        return f"SqliteTraceSink({str(self.path)!r})"


class QueuedTraceSink:
    """A bounded queue and one daemon thread in front of any sink."""

    def __init__(
        self, inner: TraceSink, maxsize: int = 10_000, on_error: Callable[[BaseException], None] | None = None
    ) -> None:
        if maxsize < 1:
            raise ValueError("maxsize must be at least 1")
        self.inner = inner
        self.on_error = on_error
        self._queue: queue.Queue[TraceEvent | None] = queue.Queue(maxsize)
        self._lock = threading.Lock()
        self.recorded = 0
        self.dropped = 0
        self.errors = 0
        self._closed = False
        self._thread = threading.Thread(target=self._drain, name="praxis-trace-sink", daemon=True)
        self._thread.start()

    def record(self, trace: TraceEvent) -> None:
        """Enqueue and return. A full queue drops the trace and counts it; nothing blocks."""
        if self._closed:
            with self._lock:
                self.dropped += 1
            return
        try:
            self._queue.put_nowait(trace)
        except queue.Full:
            with self._lock:
                self.dropped += 1

    def _drain(self) -> None:
        while True:
            item = self._queue.get()
            try:
                if item is None:
                    return
                try:
                    self.inner.record(item)
                    with self._lock:
                        self.recorded += 1
                except BaseException as exc:  # noqa: BLE001 - counted, never raised
                    with self._lock:
                        self.errors += 1
                    if self.on_error is not None:
                        with contextlib.suppress(BaseException):  # a hook that raises must not either
                            self.on_error(exc)
            finally:
                self._queue.task_done()

    def flush(self, timeout: float | None = 5.0) -> bool:
        """Wait until everything enqueued so far has been handed to the inner sink.
        Returns False if the timeout passed first."""
        deadline = None if timeout is None else time.monotonic() + timeout
        while self._queue.unfinished_tasks:
            if deadline is not None and time.monotonic() >= deadline:
                return False
            time.sleep(0.001)
        return True

    def read(self, capability: str | None = None) -> Iterator[TraceEvent]:
        self.flush()
        yield from self.inner.read(capability)

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "recorded": self.recorded,
                "dropped": self.dropped,
                "errors": self.errors,
                "queued": self._queue.qsize(),
                "closed": self._closed,
            }

    def close(self, timeout: float | None = 5.0) -> bool:
        """Drain what is queued, stop the thread. Later ``record`` calls are counted as dropped."""
        if self._closed:
            return True
        self._closed = True
        try:
            self._queue.put(None, timeout=timeout)
        except queue.Full:
            return False
        self._thread.join(timeout)
        return not self._thread.is_alive()

    def __enter__(self) -> QueuedTraceSink:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def __repr__(self) -> str:
        return f"QueuedTraceSink({self.inner!r})"
