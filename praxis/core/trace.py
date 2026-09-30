"""Trace sinks: JSONL (the default) and SQLite. Both standard library, both readable back.

The router never lets a sink failure reach the caller, so a sink may raise freely. What a
sink must do is round-trip: ``read()`` yields the same ``TraceEvent`` that ``record()``
was given. Late-bound fields (``outcome``, ``feedback``) are updated by re-recording the
trace; SQLite replaces by ``trace_id``, JSONL appends and the reader keeps the last.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Iterator

from .contracts import TraceEvent


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
                (trace.trace_id, trace.capability, trace.created_at, trace.stage, trace.answered_by,
                 1 if trace.abstain else 0, trace.host_partition, trace.to_json()))
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
