"""Phase 0: the contracts round-trip, the fakes satisfy the ports, the package outside
``providers`` is standard library only, and a fake end-to-end decide() returns a DecisionResult."""

from __future__ import annotations

import ast
import importlib.util
import json
import pathlib
import re
import subprocess
import sys
import unittest

from praxis_core.contracts import (
    ENVELOPE_VERSION,
    Budget,
    Capability,
    DecisionExample,
    DecisionRequest,
    DecisionResult,
    ModelArtifact,
    ModelInfo,
    Question,
    QuestionTrace,
    RequestContext,
    TraceEvent,
    normalise_question_type,
)
from praxis_core.ports import (
    Calibrator,
    DecisionModel,
    GenerativeModel,
    Registry,
    SchemaValidator,
    Teacher,
    TraceSink,
    Trainer,
)
from praxis_core.providers.fake import (
    FakeCalibrator,
    FakeDecisionModel,
    FakeGenerativeModel,
    FakeRegistry,
    FakeSchemaValidator,
    FakeTeacher,
    FakeTraceSink,
    FakeTrainer,
)
from praxis_core.router import DecisionRouter, RoutingPolicy
from tests.helpers import DEPARTMENTS, URGENCY, oracle, triage_capability

ROOT = pathlib.Path(__file__).resolve().parent.parent


class QuestionsAreTyped(unittest.TestCase):
    def test_noul_is_accepted_as_an_alias_and_written_as_boolean(self):
        q = Question("noul", "Is it raining?")  # type: ignore[arg-type]
        self.assertEqual(q.type, "boolean")
        self.assertEqual(q.to_dict()["type"], "boolean")
        self.assertEqual(normalise_question_type("NOUL"), "boolean")

    def test_an_unknown_type_is_refused(self):
        with self.assertRaises(ValueError):
            normalise_question_type("vibe")

    def test_a_choice_needs_two_options(self):
        with self.assertRaises(ValueError):
            Question.choice("Pick", {"only": "one"})

    def test_a_score_needs_two_described_levels(self):
        with self.assertRaises(ValueError):
            Question.score("Rate", ["one"])
        with self.assertRaises(ValueError):
            Question.score("Rate", ["low", ""])

    def test_a_boolean_takes_no_options(self):
        with self.assertRaises(ValueError):
            Question("boolean", "Yes?", {"a": "x", "b": "y"})

    def test_instructions_are_required(self):
        with self.assertRaises(ValueError):
            Question.boolean("   ")

    def test_keys_per_type(self):
        self.assertEqual(Question.choice("c", {"a": "A", "b": "B"}).keys(), ("a", "b"))
        self.assertEqual(Question.score("s", ["l", "m", "h"]).keys(), ("0", "1", "2"))
        self.assertEqual(Question.boolean("b").keys(), ("true", "false"))
        self.assertEqual(Question.rank("r", {"x": "X", "y": "Y"}).keys(), ("x", "y"))

    def test_rank_is_derived_from_choice(self):
        r = Question.rank("Order these", {"x": "X", "y": "Y"})
        self.assertEqual(r.as_choice().type, "choice")
        self.assertEqual(r.as_choice().options, r.options)
        self.assertTrue(r.is_valid_answer(["y", "x"]))
        self.assertFalse(r.is_valid_answer(["y"]))
        self.assertEqual(r.key_for(["y", "x"]), "y")

    def test_keys_and_answers_round_trip_per_type(self):
        c = Question.choice("c", {"a": "A", "b": "B"})
        s = Question.score("s", ["low", "mid", "high"])
        b = Question.boolean("b")
        self.assertEqual(c.answer_for(c.key_for("b")), "b")
        self.assertEqual(s.answer_for(s.key_for(2)), 2)
        self.assertIs(b.answer_for(b.key_for(True)), True)
        self.assertIs(b.answer_for(b.key_for(False)), False)
        with self.assertRaises(ValueError):
            c.key_for("z")
        with self.assertRaises(ValueError):
            s.key_for(7)
        with self.assertRaises(ValueError):
            b.key_for("maybe")

    def test_describe_is_human_readable(self):
        cap = triage_capability()
        self.assertEqual(cap.questions["urgency"].describe(3), URGENCY[3])
        self.assertEqual(cap.questions["department"].describe("sales"), DEPARTMENTS["sales"])
        self.assertEqual(cap.questions["churn_risk"].describe(True), "yes")

    def test_the_definition_hash_moves_when_an_option_moves(self):
        a = Question.choice("c", {"a": "A", "b": "B"})
        b = Question.choice("c", {"a": "A", "b": "B (edited)"})
        self.assertNotEqual(a.definition_hash, b.definition_hash)
        self.assertEqual(a.definition_hash, Question.from_dict(a.to_dict()).definition_hash)


class CapabilitiesDeclareTheirKind(unittest.TestCase):
    def test_the_name_is_domain_dot_operation(self):
        with self.assertRaises(ValueError):
            Capability("triage", questions={"q": Question.boolean("b")})

    def test_a_decision_capability_needs_questions(self):
        with self.assertRaises(ValueError):
            Capability("support.triage")

    def test_a_generative_capability_needs_a_schema(self):
        with self.assertRaises(ValueError):
            Capability("support.reply", kind="generative", instructions="Write a reply.")
        cap = Capability(
            "support.reply", kind="generative", instructions="Write a reply.", output_schema={"reply": "str"}
        )
        self.assertEqual(cap.kind, "generative")

    def test_request_carries_the_declared_questions(self):
        cap = triage_capability()
        req = cap.request({"subject": "x"}, RequestContext(host_partition="tenant-a"))
        self.assertEqual(req.capability, "support.triage")
        self.assertEqual(set(req.questions), {"department", "urgency", "churn_risk"})
        self.assertEqual(req.context.host_partition, "tenant-a")


def _trace() -> TraceEvent:
    cap = triage_capability()
    q = cap.questions["department"]
    return TraceEvent(
        trace_id="t1",
        capability=cap.name,
        capability_kind="decision",
        capability_hash=cap.definition_hash,
        stage="shadow",
        answered_by="system2",
        abstain=False,
        state={"subject": "invoice wrong"},
        questions=[
            QuestionTrace(
                "department",
                "choice",
                q.definition_hash,
                q,
                "system2",
                False,
                answer="billing",
                system1_answer="technical",
                system2_answer="billing",
                raw_distribution={"billing": 0.4, "technical": 0.6, "account": 0.0, "sales": 0.0},
                calibrated_distribution={"billing": 0.45, "technical": 0.55, "account": 0.0, "sales": 0.0},
                confidence=0.31,
                native_confidence=0.6,
                calibrator_version="temperature-v1/abc",
                system2_distribution={"billing": 1.0, "technical": 0.0, "account": 0.0, "sales": 0.0},
                reason="shadow: teacher serves; system1 recorded",
            )
        ],
        parent_trace_id=None,
        reason="",
        system1=ModelInfo("fake", "fake-system1", "0", "raw"),
        system2=ModelInfo("fake", "fake-teacher", "0"),
        system1_latency_ms=1.5,
        system2_latency_ms=20.0,
        latency_ms=22.0,
        cost_usd=0.001,
        system1_error=None,
        success=True,
        source="synthetic",
        label_candidate=True,
        host_partition="tenant-a",
        caller="tests",
        outcome={"resolved": True},
    )


class ContractsRoundTrip(unittest.TestCase):
    def test_question(self):
        for q in triage_capability().questions.values():
            self.assertEqual(Question.from_dict(json.loads(json.dumps(q.to_dict()))), q)

    def test_capability(self):
        cap = triage_capability()
        self.assertEqual(Capability.from_dict(json.loads(json.dumps(cap.to_dict()))), cap)
        gen = Capability("support.reply", kind="generative", instructions="Write.", output_schema={"reply": "str"})
        self.assertEqual(Capability.from_dict(gen.to_dict()), gen)

    def test_request_with_context_and_budget(self):
        cap = triage_capability()
        req = cap.request("the api is down", RequestContext("tenant-a", "tests", Budget(500, 0.01), {"k": 1}))
        again = DecisionRequest.from_dict(json.loads(json.dumps(req.to_dict())))
        self.assertEqual(again, req)
        self.assertEqual(again.context.budget, Budget(500, 0.01))

    def test_result(self):
        r = DecisionResult(
            "urgency",
            2,
            {"0": 0.1, "1": 0.2, "2": 0.6, "3": 0.1},
            0.42,
            0.6,
            True,
            False,
            "system1",
            "fake",
            "fake-system1",
            "0",
            "raw",
            1.2,
            0.0,
            "t1",
            1.7,
            "",
        )
        self.assertEqual(DecisionResult.from_dict(json.loads(json.dumps(r.to_dict()))), r)
        b = DecisionResult(
            "churn_risk",
            True,
            {"true": 0.9, "false": 0.1},
            0.53,
            None,
            False,
            True,
            "system2",
            "fake",
            "fake-teacher",
            "0",
            "",
            20.0,
            0.001,
            "t1",
            None,
            "below threshold",
        )
        self.assertIs(DecisionResult.from_dict(json.loads(json.dumps(b.to_dict()))).answer, True)

    def test_example_and_artifact(self):
        ex = DecisionExample(
            "support.triage",
            "department",
            "choice",
            {"subject": "x"},
            {"options": DEPARTMENTS},
            "billing",
            "system2",
            None,
            {"trace_id": "t1"},
        )
        self.assertEqual(DecisionExample.from_dict(json.loads(json.dumps(ex.to_dict()))), ex)
        art = ModelArtifact(
            "support.triage",
            "nn",
            "3",
            "baseline",
            "nearest-neighbour",
            "",
            "file:///x",
            {"acc": 0.9},
            "2026-09-30T00:00:00+00:00",
        )
        self.assertEqual(ModelArtifact.from_dict(json.loads(json.dumps(art.to_dict()))), art)

    def test_trace_envelope_v2(self):
        t = _trace()
        self.assertEqual(t.envelope_version, ENVELOPE_VERSION)
        again = TraceEvent.from_json(t.to_json())
        self.assertEqual(again, t)
        self.assertEqual(again.question("department").system2_answer, "billing")
        self.assertEqual(again.input_key, t.input_key)

    def test_an_unknown_envelope_version_is_refused(self):
        d = _trace().to_dict()
        d["envelope_version"] = 99
        with self.assertRaises(ValueError):
            TraceEvent.from_dict(d)


class TheFakesSatisfyThePorts(unittest.TestCase):
    def test_one_fake_per_port(self):
        self.assertIsInstance(FakeDecisionModel(), DecisionModel)
        self.assertIsInstance(FakeGenerativeModel(), GenerativeModel)
        self.assertIsInstance(FakeTeacher(), Teacher)
        self.assertIsInstance(FakeCalibrator(), Calibrator)
        self.assertIsInstance(FakeTrainer(), Trainer)
        self.assertIsInstance(FakeTraceSink(), TraceSink)
        self.assertIsInstance(FakeSchemaValidator(), SchemaValidator)
        self.assertIsInstance(FakeRegistry(), Registry)

    def test_the_fake_registry_and_trainer_close_the_loop(self):
        ex = DecisionExample("support.triage", "department", "choice", "x", {}, "billing")
        art = FakeTrainer().train([ex, ex])
        reg = FakeRegistry()
        reg.register(art)
        reg.set_stage(art.capability, art.version, "shadow")
        self.assertEqual(reg.get("support.triage"), art)
        self.assertEqual(reg.manifest("support.triage")["versions"][0]["stage"], "shadow")
        with self.assertRaises(KeyError):
            reg.set_stage("support.triage", "nope", "serve")


class TheCoreIsStandardLibraryOnly(unittest.TestCase):
    VENDOR_WORDS = ("jev", "laya", "anyjev", "openai", "anthropic", "typesafe", "nokia", "convai", "vllm", "litellm")

    def _imports(self, path: pathlib.Path) -> set[str]:
        tree = ast.parse(path.read_text())
        names: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names.add(node.module.split(".")[0])
        return names

    @staticmethod
    def _core_files() -> list[pathlib.Path]:
        """Every module of the package except the adapters."""
        files = [p for p in (ROOT / "praxis_core").rglob("*.py") if "providers" not in p.parts]
        assert len(files) >= 10, "the package tree moved; this gate would be vacuous"
        return files

    def test_core_imports_only_the_standard_library(self):
        for path in self._core_files():
            for name in self._imports(path):
                self.assertTrue(
                    name == "praxis_core" or name in sys.stdlib_module_names,
                    f"{path.relative_to(ROOT)} imports {name}, which is not standard library",
                )

    def test_no_provider_name_appears_outside_providers(self):
        for path in self._core_files():
            text = path.read_text().lower()
            for word in self.VENDOR_WORDS:
                self.assertIsNone(re.search(rf"\b{word}\b", text), f"{path.relative_to(ROOT)} mentions {word!r}")


class AFakeEndToEndDecideReturnsAResult(unittest.TestCase):
    def test_decide_returns_one_result_per_question_and_records_a_trace(self):
        cap = triage_capability()
        sink = FakeTraceSink()
        router = DecisionRouter(
            cap,
            FakeTeacher(oracle),
            FakeDecisionModel(peak=0.97),
            FakeCalibrator(fitted=True),
            sink,
            RoutingPolicy(threshold=0.5, stage="serve"),
        )
        results = router.decide(cap.request({"subject": "invoice charged twice", "body": "please refund"}))
        self.assertEqual(set(results), {"department", "urgency", "churn_risk"})
        for name, result in results.items():
            self.assertIsInstance(result, DecisionResult)
            self.assertEqual(result.question, name)
            self.assertEqual(DecisionResult.from_dict(result.to_dict()), result)
            self.assertAlmostEqual(sum(result.distribution.values()), 1.0, places=6)
        self.assertEqual(results["department"].answered_by, "system1")
        self.assertAlmostEqual(
            results["urgency"].expected_value or 0.0, 0.06, places=9
        )  # 0.97 on level 0, 0.01 on each of 1, 2, 3
        self.assertEqual(len(sink.traces), 1)
        self.assertEqual(sink.traces[0].trace_id, results["department"].trace_id)
        self.assertEqual(TraceEvent.from_json(sink.traces[0].to_json()), sink.traces[0])

    def test_a_generative_capability_is_refused_by_the_decision_router(self):
        gen = Capability("support.reply", kind="generative", instructions="Write.", output_schema={"reply": "str"})
        with self.assertRaises(ValueError):
            DecisionRouter(gen, FakeTeacher())


@unittest.skipUnless(importlib.util.find_spec("mypy"), "mypy is not installed in this interpreter")
class MypyStrictIsCleanOnTheCore(unittest.TestCase):
    def test_mypy_strict(self):
        proc = subprocess.run(
            [sys.executable, "-m", "mypy"],  # scope and strictness come from pyproject.toml
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
