"""``python -m praxis_core demo`` stays green: support.triage, fake teacher, baseline student,
under one second, no installs, no keys."""

from __future__ import annotations

import json
import pathlib
import re
import subprocess
import sys
import tempfile
import time
import unittest

from praxis_core.demo import TicketGenerator, rule_teacher, run_demo, support_triage

ROOT = pathlib.Path(__file__).resolve().parent.parent


class TheDemoStaysGreen(unittest.TestCase):
    def test_it_closes_the_loop_in_under_a_second(self):
        lines: list[str] = []
        summary = run_demo(out=lines.append)
        self.assertLess(summary.elapsed_ms, 1000.0)
        self.assertEqual([s.stage for s in summary.stages], ["observe", "shadow-warm", "canary-50%", "serve"])
        cold, warm, canary, serve = summary.stages
        self.assertEqual(cold.system1_share, 0.0)
        self.assertEqual(warm.system1_share, 0.0)
        self.assertGreater(warm.agreement or 0.0, cold.agreement or 0.0, "a fitted student agrees more")
        self.assertGreater(serve.system1_share, 0.0)
        self.assertGreater(serve.abstain_share, 0.0)
        self.assertEqual(summary.trace_count, 240)
        self.assertEqual(summary.examples, 180)
        self.assertEqual(set(summary.temperatures), {"boolean/2", "choice/4", "score/4"})
        self.assertLessEqual(summary.confident_wrong, summary.served_by_system1)
        self.assertTrue(any(line.startswith("loop closed in") for line in lines))
        self.assertEqual([s.stage for s in summary.extract_stages], ["observe", "shadow-warm", "canary-50%", "serve"])
        self.assertEqual(summary.extract_trace_count, 240)
        self.assertEqual(summary.extract_examples, 60)
        self.assertLessEqual(summary.extract_confident_wrong, summary.extract_served_by_system1)
        self.assertTrue(any("support.extract" in line for line in lines))
        self.assertTrue(summary.verdict.startswith("ready for canary"), summary.verdict)
        self.assertTrue(summary.extract_verdict.startswith("stays in shadow"), summary.extract_verdict)
        self.assertEqual(summary.extract_served_by_system1, 0, "nothing is served without a fitted calibrator")

    def test_it_is_deterministic_for_a_seed(self):
        a, b = run_demo(out=None).as_dict(), run_demo(out=None).as_dict()
        for d in (a, b):
            d.pop("elapsed_ms")
            for stage in d["stages"] + d["extract"]["stages"]:
                stage.pop("elapsed_ms")
        self.assertEqual(a, b)

    def test_the_module_entry_point_runs_with_nothing_installed(self):
        started = time.perf_counter()
        proc = subprocess.run(
            [sys.executable, "-m", "praxis_core", "demo", "--tickets", "30"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            env={"PATH": "", "PYTHONDONTWRITEBYTECODE": "1"},
        )
        wall = time.perf_counter() - started
        self.assertEqual(proc.returncode, 0, proc.stderr)
        match = re.search(r"loop closed in (\d+) ms", proc.stdout)
        self.assertIsNotNone(match, proc.stdout)
        self.assertLess(int(match.group(1)), 1000)
        self.assertLess(wall, 5.0)

    def test_json_output_and_a_jsonl_sink(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "traces.jsonl"
            proc = subprocess.run(
                [sys.executable, "-m", "praxis_core", "demo", "--tickets", "10", "--json", "--jsonl", str(path)],
                cwd=ROOT,
                capture_output=True,
                text=True,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            summary = json.loads(proc.stdout)
            self.assertEqual(
                len(path.read_text().splitlines()), summary["trace_count"] + summary["extract"]["trace_count"]
            )

    def test_version_flag(self):
        proc = subprocess.run(
            [sys.executable, "-m", "praxis_core", "--version"], cwd=ROOT, capture_output=True, text=True
        )
        self.assertEqual(proc.returncode, 0)
        self.assertIn("praxis 0.3", proc.stdout)


class TheTrafficAndTheTeacherAreHonest(unittest.TestCase):
    def test_the_generator_is_deterministic_and_varied(self):
        a, b = TicketGenerator(3).tickets(20), TicketGenerator(3).tickets(20)
        self.assertEqual(a, b)
        self.assertGreater(len({t["body"] for t in a}), 15)

    def test_the_extract_teacher_reads_the_ticket(self):
        from praxis_core.demo import PRODUCTS, extract_rule_teacher, support_extract

        cap = support_extract()
        seen_products, seen_orders, seen_issues = set(), 0, set()
        for ticket in TicketGenerator(11).tickets(200):
            out = extract_rule_teacher(ticket, cap.instructions, cap.output_schema)
            self.assertEqual(set(out), set(cap.output_schema))
            seen_products.add(out["product"])
            seen_issues.add(out["issue"])
            seen_orders += bool(out["order_id"])
        self.assertEqual(seen_products, set(PRODUCTS) | {""})
        self.assertGreater(seen_orders, 50)
        self.assertNotIn("", seen_issues, "every generated phrase has an issue tag")

    def test_the_teacher_reads_the_ticket_and_covers_every_answer(self):
        cap = support_triage()
        seen = {name: set() for name in cap.questions}
        for ticket in TicketGenerator(11).tickets(200):
            for name, question in cap.questions.items():
                answer = rule_teacher(ticket, name, question)
                self.assertTrue(question.is_valid_answer(answer), (name, answer))
                seen[name].add(question.key_for(answer))
        for name, question in cap.questions.items():
            self.assertEqual(seen[name], set(question.keys()), f"{name}: every answer occurs")


if __name__ == "__main__":
    unittest.main(verbosity=2)
