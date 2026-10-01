"""JSONL and SQLite sinks round-trip the envelope and read back by capability."""

from __future__ import annotations

import json
import pathlib
import tempfile
import time
import unittest

from praxis_core.contracts import Question, QuestionTrace, TraceEvent
from praxis_core.demo import run_demo
from praxis_core.ports import TraceSink
from praxis_core.providers.fake import FakeTraceSink
from praxis_core.trace import JsonlTraceSink, QueuedTraceSink, SqliteTraceSink
from tests.helpers import triage_capability

CAP = triage_capability()


def trace(i: int, capability: str = CAP.name) -> TraceEvent:
    q: Question = CAP.questions["churn_risk"]
    return TraceEvent(
        trace_id=f"t{i}",
        capability=capability,
        capability_kind="decision",
        capability_hash=CAP.definition_hash,
        stage="serve",
        answered_by="system1",
        abstain=False,
        state={"subject": f"ticket {i}"},
        created_at=f"2026-09-30T00:00:0{i}+00:00",
        questions=[
            QuestionTrace(
                "churn_risk",
                "boolean",
                q.definition_hash,
                q,
                "system1",
                False,
                answer=True,
                system1_answer=True,
                raw_distribution={"true": 0.9, "false": 0.1},
                calibrated_distribution={"true": 0.9, "false": 0.1},
                confidence=0.53,
            )
        ],
        host_partition="tenant-a",
    )


class BothSinksRoundTrip(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = pathlib.Path(self.tmp.name)
        self.sqlite = SqliteTraceSink(base / "traces.db")
        self.sinks = {"jsonl": JsonlTraceSink(base / "traces.jsonl"), "sqlite": self.sqlite}

    def tearDown(self):
        self.sqlite.close()
        self.tmp.cleanup()

    def test_they_satisfy_the_port(self):
        for sink in self.sinks.values():
            self.assertIsInstance(sink, TraceSink)

    def test_record_then_read_returns_equal_traces_filtered_by_capability(self):
        for name, sink in self.sinks.items():
            with self.subTest(sink=name):
                originals = [trace(1), trace(2), trace(3, "support.other")]
                for t in originals:
                    sink.record(t)
                self.assertEqual(list(sink.read()), originals)
                self.assertEqual(list(sink.read(CAP.name)), originals[:2])
                self.assertEqual(list(sink.read("support.none")), [])

    def test_re_recording_a_trace_keeps_the_latest_version(self):
        for name, sink in self.sinks.items():
            with self.subTest(sink=name):
                first = trace(4)
                sink.record(first)
                updated = TraceEvent.from_dict(first.to_dict())
                updated.outcome = {"resolved": True}
                sink.record(updated)
                read = [t for t in sink.read() if t.trace_id == "t4"]
                self.assertEqual(len(read), 1)
                self.assertEqual(read[0].outcome, {"resolved": True})

    def test_reading_a_missing_jsonl_file_is_empty(self):
        self.assertEqual(list(JsonlTraceSink(pathlib.Path(self.tmp.name) / "nope.jsonl").read()), [])

    def test_sqlite_counts(self):
        self.sqlite.record(trace(5))
        self.sqlite.record(trace(6, "support.other"))
        self.assertEqual(self.sqlite.count(), 2)
        self.assertEqual(self.sqlite.count(CAP.name), 1)

    def test_the_demo_writes_every_trace_to_a_real_sink(self):
        path = pathlib.Path(self.tmp.name) / "demo.jsonl"
        summary = run_demo(tickets=10, sink=JsonlTraceSink(path), out=None)
        lines = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
        self.assertEqual(len(lines), summary.trace_count + summary.extract_trace_count)
        self.assertTrue(all(line["envelope_version"] == 2 for line in lines))
        with SqliteTraceSink(pathlib.Path(self.tmp.name) / "demo.db") as db:
            summary = run_demo(tickets=10, sink=db, out=None)
            self.assertEqual(db.count(), summary.trace_count + summary.extract_trace_count)


class TheBackgroundSinkCostsTheCallerNothing(unittest.TestCase):
    """PX-101: capture adds no visible latency, drops are counted, failures never raise."""

    def test_record_is_microseconds_and_nothing_is_lost(self):
        with (
            tempfile.TemporaryDirectory() as tmp,
            SqliteTraceSink(pathlib.Path(tmp) / "q.db") as db,
            QueuedTraceSink(db) as sink,
        ):
            self.assertIsInstance(sink, TraceSink)
            timings = []
            for i in range(1000):
                started = time.perf_counter()
                sink.record(trace(i))
                timings.append((time.perf_counter() - started) * 1000.0)
            self.assertTrue(sink.flush(timeout=30))
            p95 = sorted(timings)[int(0.95 * len(timings)) - 1]
            self.assertLess(p95, 5.0, f"p95 {p95:.3f} ms")
            self.assertEqual(db.count(), 1000)
            self.assertEqual(sink.stats()["recorded"], 1000)
            self.assertEqual(sink.stats()["dropped"], 0)

    def test_a_full_queue_drops_and_counts_instead_of_blocking(self):
        class Slow(FakeTraceSink):
            def record(self, t):
                time.sleep(0.02)
                super().record(t)

        slow = Slow()
        sink = QueuedTraceSink(slow, maxsize=5)
        started = time.perf_counter()
        for i in range(60):
            sink.record(trace(i))
        self.assertLess(time.perf_counter() - started, 0.5, "record never blocks")
        sink.close(timeout=10)
        stats = sink.stats()
        self.assertGreater(stats["dropped"], 0)
        self.assertEqual(stats["recorded"] + stats["dropped"], 60)
        self.assertEqual(len(slow.traces), stats["recorded"])

    def test_an_inner_failure_is_counted_not_raised(self):
        seen: list[BaseException] = []
        sink = QueuedTraceSink(FakeTraceSink(fail=OSError("disk full")), on_error=seen.append)
        sink.record(trace(1))
        sink.record(trace(2))
        self.assertTrue(sink.flush())
        self.assertEqual(sink.stats()["errors"], 2)
        self.assertEqual(len(seen), 2)
        sink.close()

    def test_read_flushes_first_and_close_stops_accepting(self):
        inner = FakeTraceSink()
        sink = QueuedTraceSink(inner)
        sink.record(trace(7))
        self.assertEqual([t.trace_id for t in sink.read()], ["t7"])
        self.assertTrue(sink.close())
        sink.record(trace(8))
        self.assertEqual(sink.stats()["dropped"], 1)
        self.assertEqual(len(inner.traces), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
