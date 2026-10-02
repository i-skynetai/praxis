"""The README's five steps run as written (PX-902).

The four Python blocks in "Use it in your own project" are executed verbatim, in order,
in one namespace. The test supplies only what the README leaves to the reader: the
app's own model (``my_big_model``), the teacher (``my_teacher``) and the tickets. Where
the README says "keep observing", the test repeats the README's own observe line over
synthetic tickets. If a block stops running, or step 5 stops behaving as its comments
say, this test fails before a reader finds out.
"""

from __future__ import annotations

import contextlib
import io
import os
import pathlib
import re
import tempfile
import unittest
from typing import Any

from praxis_core import DecisionResult, ModelInfo, NotReady, Question
from praxis_core.demo import TicketGenerator
from praxis_core.providers.fake import FakeTeacher

ROOT = pathlib.Path(__file__).resolve().parent.parent
README = (ROOT / "README.md").read_text(encoding="utf-8")


def python_blocks() -> list[str]:
    return re.findall(r"```python\n(.*?)```", README, flags=re.DOTALL)


def text_of(ticket: Any) -> str:
    return " ".join(str(v) for v in ticket.values()).lower() if isinstance(ticket, dict) else str(ticket).lower()


def readers_model(ticket: Any, name: str, question: Question) -> Any:
    """Stands in for the reader's own big model: keyword rules over the README's options."""
    text = text_of(ticket)
    if name == "department":
        return "billing" if re.search(r"invoice|refund|charge|bill|payment|card", text) else "technical"
    if name == "urgency":
        if re.search(r"down|outage|urgent|asap|immediately", text):
            return 3
        if re.search(r"today|soon|blocked", text):
            return 2
        return 1 if re.search(r"error|fail|broken|cannot", text) else 0
    return bool(re.search(r"cancel|switch|leave|competitor", text))


@contextlib.contextmanager
def inside(path: str):
    before = os.getcwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(before)


class TheReadmeStepsRunAsWritten(unittest.TestCase):
    def test_there_are_four_python_steps(self):
        self.assertEqual(len(python_blocks()), 4, "steps 2 to 5")

    def test_steps_two_to_five(self):
        step2, step3, step4, step5 = python_blocks()
        teacher = FakeTeacher(readers_model)
        tickets = TicketGenerator(21).tickets(200)
        ns: dict[str, Any] = {"my_teacher": teacher, "ticket": tickets[0]}

        def my_big_model(ticket: Any) -> dict[str, Any]:
            triage = ns["triage"]
            return {name: readers_model(ticket, name, q) for name, q in triage.questions.items()}

        ns["my_big_model"] = my_big_model

        def keep_observing(batch: list[Any]) -> None:  # the README's own observe line, repeated
            for ticket in batch:
                ns["router"].observe_state(
                    ticket, my_big_model(ticket), ModelInfo("my-provider", "big-model"), latency_ms=820
                )

        with tempfile.TemporaryDirectory() as tmp, inside(tmp):
            exec(step2, ns)  # declare
            exec(step3, ns)  # capture one call
            self.assertEqual(ns["router"].policy.stage, "shadow", "shadow by default")
            keep_observing(tickets[1:80])

            exec(step4, ns)  # fit a student, new router, still shadow
            self.assertGreater(ns["report"]["examples"], 0)
            self.assertEqual(ns["router"].policy.stage, "shadow")
            keep_observing(tickets[80:200])
            with self.assertRaises(NotReady, msg="no calibrator fitted yet"):
                ns["router"].set_stage("canary")

            printed = io.StringIO()
            with contextlib.redirect_stdout(printed):
                exec(step5, ns)  # fit the calibrator, print the verdict, canary, decide
            self.assertTrue(printed.getvalue().startswith("ready: "), printed.getvalue())
            verdict = ns["router"].readiness()
            self.assertTrue(verdict.ready, verdict.verdict)
            self.assertTrue(verdict.verdict.startswith("ready: "), verdict.verdict)
            self.assertEqual(ns["router"].policy.stage, "canary")
            result = ns["result"]
            self.assertIsInstance(result, DecisionResult)
            self.assertIn(result.answer, (0, 1, 2, 3))
            self.assertIn(result.answered_by, ("system1", "system2"))
            self.assertTrue((pathlib.Path(tmp) / "traces.jsonl").exists(), "step 3 wrote the trace file")


if __name__ == "__main__":
    unittest.main(verbosity=2)
