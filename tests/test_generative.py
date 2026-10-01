"""PX-070 and PX-080: generative capabilities through the same router, with the validator as
the hard gate and a scalar calibrator on the student's self-reported confidence. The
fault-injection guarantees hold exactly as for the decision kind."""
from __future__ import annotations

import json
import random
import unittest

from praxis_core.baseline import NearestNeighbourGenerativeModel
from praxis_core.calibrate import PlattCalibrator, fit_platt, sigmoid
from praxis_core.contracts import (
    Capability,
    GenerationTrace,
    GenerativeExample,
    GenerativeRequest,
    GenerativeResult,
    ModelInfo,
    RequestContext,
    TraceEvent,
    normalise_output,
    outputs_match,
)
from praxis_core.dataset import generative_examples_from_traces
from praxis_core.ports import GenerativeModel, ScalarCalibrator
from praxis_core.router import GenerativeRouter, RoutingPolicy, TeacherError
from praxis_core.providers.fake import (
    GENERATIVE_MALFORMED_MODES,
    FakeGenerativeModel,
    FakeScalarCalibrator,
    FakeTraceSink,
)
from praxis_core.demo import extract_rule_teacher, support_extract
from tests.helpers import TicketGenerator

CAP = support_extract()
TICKET = {"subject": "invoice charged twice", "body": "hi, why was I charged twice on the invoice for my Nimbus router, "
                                                    "order #AB1234. we need this today."}
EXPECTED = extract_rule_teacher(TICKET, CAP.instructions, CAP.output_schema)
APP = ModelInfo("app", "the-apps-own-model", "2026-10")


def teacher() -> FakeGenerativeModel:
    return FakeGenerativeModel(extract_rule_teacher, info=ModelInfo("fake", "fake-generative-teacher", "0"))


def make(system1=None, *, policy=None, sink=None, calibrator=None, teacher_model=None, rng=None, match=None,
         on_trace_error=None):
    sink = sink if sink is not None else FakeTraceSink()
    t = teacher_model or teacher()
    router = GenerativeRouter(CAP, t, system1, calibrator, sink, policy or RoutingPolicy(threshold=0.5),
                              match=match, rng=rng, on_trace_error=on_trace_error)
    return router, sink, t


class TheContractsRoundTrip(unittest.TestCase):
    def test_request_result_example_and_generation_trace(self):
        req = CAP.generative_request(TICKET, RequestContext("tenant-a", "tests"))
        self.assertEqual(GenerativeRequest.from_dict(json.loads(json.dumps(req.to_dict()))), req)
        res = GenerativeResult(EXPECTED, 0.8, 0.9, True, False, "system1", "fake", "m", "1", "", 3.0, 0.0, "t1", True, "")
        self.assertEqual(GenerativeResult.from_dict(json.loads(json.dumps(res.to_dict()))), res)
        ex = GenerativeExample(CAP.name, TICKET, EXPECTED, "system2", {"trace_id": "t1"})
        self.assertEqual(GenerativeExample.from_dict(json.loads(json.dumps(ex.to_dict()))), ex)
        g = GenerationTrace("system2", False, EXPECTED, {"product": "x"}, EXPECTED, True, 0.4, 0.9, "platt-v1/abc", False, "r")
        self.assertEqual(GenerationTrace.from_dict(json.loads(json.dumps(g.to_dict()))), g)

    def test_the_default_match_is_exact_after_normalisation(self):
        self.assertTrue(outputs_match({"product": " Nimbus Router "}, {"product": "nimbus router"}))
        self.assertFalse(outputs_match({"product": "nimbus"}, {"product": "atlas"}))
        self.assertEqual(normalise_output(["A  b", 1, {"K": "V"}]), ["a b", 1, {"K": "v"}])

    def test_the_fakes_satisfy_the_ports(self):
        self.assertIsInstance(FakeGenerativeModel(), GenerativeModel)
        self.assertIsInstance(FakeScalarCalibrator(), ScalarCalibrator)
        self.assertIsInstance(PlattCalibrator(), ScalarCalibrator)
        self.assertIsInstance(NearestNeighbourGenerativeModel(), GenerativeModel)

    def test_a_decision_capability_is_refused(self):
        from tests.helpers import triage_capability
        with self.assertRaises(ValueError):
            GenerativeRouter(triage_capability(), teacher())


class FaultInjectionNeverFailsTheCall(unittest.TestCase):
    def assert_from_teacher(self, result: GenerativeResult, sink: FakeTraceSink, prefix: str) -> None:
        self.assertEqual(result.answered_by, "system2")
        self.assertTrue(result.abstain)
        self.assertTrue(result.reason.startswith(prefix), result.reason)
        self.assertEqual(result.output, EXPECTED)
        trace = sink.traces[-1]
        self.assertTrue(trace.success and trace.label_candidate and trace.abstain)
        assert trace.generation is not None
        self.assertEqual(trace.generation.answered_by, "system2")

    def test_error_timeout_and_absence(self):
        router, sink, _ = make(FakeGenerativeModel(fail=RuntimeError("boom")))
        self.assert_from_teacher(router.generate_state(TICKET), sink, "error:")
        router, sink, _ = make(FakeGenerativeModel(delay_s=0.3), policy=RoutingPolicy(0.5, system1_timeout_ms=40))
        self.assert_from_teacher(router.generate_state(TICKET), sink, "timeout:")
        router, sink, _ = make(None)
        self.assert_from_teacher(router.generate_state(TICKET), sink, "no system1")

    def test_every_malformed_mode(self):
        for mode in GENERATIVE_MALFORMED_MODES:
            with self.subTest(mode=mode):
                router, sink, _ = make(FakeGenerativeModel(extract_rule_teacher, malformed=mode))
                result = router.generate_state(TICKET)
                self.assertEqual(result.answered_by, "system2")
                self.assertTrue(result.reason.startswith(("malformed:", "invalid:")), result.reason)

    def test_a_misbehaving_calibrator(self):
        class Bad(FakeScalarCalibrator):
            def apply(self, c):
                return float("nan")
        router, sink, _ = make(FakeGenerativeModel(extract_rule_teacher, confidence=0.97), calibrator=Bad())
        self.assert_from_teacher(router.generate_state(TICKET), sink, "calibrator:")

    def test_a_hundred_hostile_calls_are_served_by_system2(self):
        hostile = [FakeGenerativeModel(fail=ValueError("x")), FakeGenerativeModel(malformed="nan-confidence"),
                   FakeGenerativeModel(malformed="invalid-output"), FakeGenerativeModel(delay_s=0.2),
                   FakeGenerativeModel(malformed="not-an-answer")]
        sink = FakeTraceSink()
        for i in range(100):
            router, _, _ = make(hostile[i % 5], sink=sink, policy=RoutingPolicy(0.5, system1_timeout_ms=20))
            self.assertEqual(router.generate_state(TICKET).answered_by, "system2")
        self.assertEqual(len(sink.traces), 100)
        self.assertTrue(all(t.success and t.abstain for t in sink.traces))

    def test_the_trace_path_never_raises(self):
        seen: list[BaseException] = []
        router, _, _ = make(FakeGenerativeModel(extract_rule_teacher, confidence=0.97),
                            sink=FakeTraceSink(fail=OSError("disk full")), on_trace_error=seen.append)
        self.assertEqual(router.generate_state(TICKET).answered_by, "system1")
        self.assertEqual(router.stats.trace_failures, 1)
        self.assertEqual(len(seen), 1)


class ServeShadowCanaryObserve(unittest.TestCase):
    def test_confident_and_valid_is_served_by_system1(self):
        router, sink, t = make(FakeGenerativeModel(extract_rule_teacher, confidence=0.97))
        r = router.generate_state(TICKET)
        self.assertEqual((r.answered_by, r.abstain, r.schema_valid, r.output), ("system1", False, True, EXPECTED))
        self.assertEqual(t.calls, 0)
        self.assertFalse(sink.traces[-1].label_candidate)

    def test_below_threshold_abstains(self):
        router, sink, t = make(FakeGenerativeModel(extract_rule_teacher, confidence=0.3))
        r = router.generate_state(TICKET)
        self.assertEqual(r.answered_by, "system2")
        self.assertTrue(r.reason.startswith("below threshold"))
        self.assertEqual(t.calls, 1)
        g = sink.traces[-1].generation
        assert g is not None
        self.assertEqual(g.system1_output, EXPECTED)
        self.assertTrue(g.matched)

    def test_shadow_records_both_and_measures_agreement(self):
        wrong = FakeGenerativeModel(lambda s, i, sch: {"product": "Atlas backup", "issue": "x", "order_id": ""}, 0.9)
        router, sink, _ = make(wrong, policy=RoutingPolicy(0.5, stage="shadow"))
        r = router.generate_state(TICKET)
        self.assertEqual((r.answered_by, r.abstain, r.output), ("system2", False, EXPECTED))
        g = sink.traces[-1].generation
        assert g is not None
        self.assertEqual(g.system2_output, EXPECTED)
        self.assertFalse(g.matched)
        self.assertEqual(router.stats.as_dict()["shadow_agreement"], 0.0)

    def test_canary_share(self):
        router, _, _ = make(FakeGenerativeModel(extract_rule_teacher, confidence=0.97),
                            policy=RoutingPolicy(0.5, stage="canary", canary_share=0.5), rng=random.Random(2))
        for _ in range(40):
            router.generate_state(TICKET)
        s = router.stats.as_dict()
        self.assertGreater(s["system1_questions"], 0)
        self.assertGreater(s["system2_questions"], 0)

    def test_calibrated_flag_and_version(self):
        router, sink, _ = make(FakeGenerativeModel(extract_rule_teacher, confidence=0.97),
                               calibrator=FakeScalarCalibrator(fitted=True))
        self.assertTrue(router.generate_state(TICKET).calibrated)
        g = sink.traces[-1].generation
        assert g is not None
        self.assertEqual(g.calibrator_version, "fake-scalar-calibrator")

    def test_a_host_match_function_is_used(self):
        loose = FakeGenerativeModel(lambda s, i, sch: {**EXPECTED, "order_id": "ab1234"}, 0.9)
        router, sink, _ = make(loose, policy=RoutingPolicy(0.5, stage="shadow"),
                               match=lambda a, b: a["product"] == b["product"] and a["issue"] == b["issue"])
        router.generate_state(TICKET)
        g = sink.traces[-1].generation
        assert g is not None
        self.assertTrue(g.matched)

    def test_require_calibrated_refuses_an_uncalibrated_student(self):
        model = FakeGenerativeModel(extract_rule_teacher, confidence=0.97)
        router, sink, _ = make(model, calibrator=FakeScalarCalibrator(fitted=False),
                               policy=RoutingPolicy(0.5, require_calibrated=True))
        r = router.generate_state(TICKET)
        self.assertEqual(r.answered_by, "system2")
        self.assertTrue(r.reason.startswith("uncalibrated"), r.reason)
        router, _, _ = make(model, calibrator=FakeScalarCalibrator(fitted=True),
                            policy=RoutingPolicy(0.5, require_calibrated=True))
        self.assertEqual(router.generate_state(TICKET).answered_by, "system1")
        router, _, _ = make(model, policy=RoutingPolicy(0.5, require_calibrated=True))
        self.assertTrue(router.generate_state(TICKET).reason.startswith("uncalibrated"), "no calibrator at all")

    def test_teacher_failure_is_recorded_then_raised(self):
        router, sink, _ = make(None, teacher_model=FakeGenerativeModel(fail=RuntimeError("boom")))
        with self.assertRaises(TeacherError):
            router.generate_state(TICKET)
        self.assertFalse(sink.traces[-1].success)
        router, sink, _ = make(None, teacher_model=FakeGenerativeModel(malformed="invalid-output"))
        with self.assertRaises(TeacherError):
            router.generate_state(TICKET)
        self.assertIn("output invalid", sink.traces[-1].error_message or "")

    def test_observe_mode_records_the_apps_output_and_replays(self):
        router, sink, t = make(FakeGenerativeModel(extract_rule_teacher, confidence=0.9))
        trace = router.observe_state(TICKET, EXPECTED, APP, latency_ms=900.0, cost_usd=0.01,
                                     context=RequestContext("tenant-a", "svc"))
        assert trace is not None
        self.assertEqual((trace.mode, trace.success, trace.label_candidate, t.calls), ("observe", True, True, 0))
        g = trace.generation
        assert g is not None
        self.assertEqual((g.system2_output, g.system1_output, g.matched), (EXPECTED, EXPECTED, True))
        again = TraceEvent.from_json(trace.to_json()).to_request()
        self.assertIsInstance(again, GenerativeRequest)
        self.assertEqual((again.capability, again.state, again.context.host_partition), (CAP.name, TICKET, "tenant-a"))
        bad = router.observe_state(TICKET, {"nope": 1}, APP)
        assert bad is not None
        self.assertFalse(bad.success)
        self.assertFalse(bad.label_candidate)
        router, _, _ = make(FakeGenerativeModel(malformed="nan-confidence"), sink=FakeTraceSink(fail=OSError("x")))
        for output in (EXPECTED, None, "text", object()):
            self.assertTrue(router.observe_state(TICKET, output, APP) is not None)
        self.assertEqual(router.stats.observe_failures, 0)


class ThePlattCalibrator(unittest.TestCase):
    @staticmethod
    def synthetic(rng: random.Random, n: int, over: float) -> list[TraceEvent]:
        """A student whose reported confidence c relates to the true P(right) as sigmoid(logit(p)*over)."""
        from praxis_core.calibrate import logit
        traces = []
        for i in range(n):
            p = rng.uniform(0.05, 0.95)              # the true chance the output is right
            reported = sigmoid(over * logit(p))       # over > 1: the student is over-confident
            matched = rng.random() < p
            traces.append(TraceEvent(trace_id=f"g{i}", capability=CAP.name, capability_kind="generative",
                                     capability_hash="h", stage="shadow", answered_by="system2", abstain=False,
                                     questions=[], state=f"s{i}",
                                     generation=GenerationTrace("system2", False, native_confidence=reported, matched=matched)))
        return traces

    def test_an_over_confident_student_is_softened_and_calibration_improves(self):
        rng = random.Random(5)
        train, held = self.synthetic(rng, 600, 2.5), self.synthetic(rng, 600, 2.5)
        cal = PlattCalibrator()
        params = cal.fit(train)
        self.assertTrue(cal.is_fitted())
        self.assertLess(params["a"], 0.6, "slope below one undoes the over-confidence")
        from praxis_core.calibrate import expected_calibration_error
        pairs = PlattCalibrator.pairs_from(held)
        before = expected_calibration_error([c for c, _ in pairs], [ok for _, ok in pairs])
        after = expected_calibration_error([cal.apply(c) for c, _ in pairs], [ok for _, ok in pairs])
        self.assertLess(after, before)
        self.assertLess(after, 0.08)

    def test_unfitted_is_identity_and_small_samples_are_skipped(self):
        cal = PlattCalibrator(min_examples=50)
        self.assertEqual(cal.apply(0.8), 0.8)
        cal.fit(self.synthetic(random.Random(1), 20, 1.0))
        self.assertFalse(cal.is_fitted())
        self.assertEqual(cal.skipped, 20)

    def test_parameters_round_trip(self):
        cal = PlattCalibrator()
        cal.fit(self.synthetic(random.Random(2), 200, 0.5))
        again = PlattCalibrator.from_dict(cal.to_dict())
        self.assertEqual(again.version, cal.version)
        self.assertAlmostEqual(again.apply(0.7), cal.apply(0.7))

    def test_fit_platt_recovers_a_known_map(self):
        rng = random.Random(3)
        pairs = []
        for _ in range(2000):
            x = rng.uniform(-3, 3)
            c = sigmoid(x)
            pairs.append((c, rng.random() < sigmoid(0.5 * x - 0.3)))
        a, b = fit_platt(pairs)
        self.assertAlmostEqual(a, 0.5, delta=0.12)
        self.assertAlmostEqual(b, -0.3, delta=0.12)


class TheGenerativeBaselineAndDataset(unittest.TestCase):
    def test_unfitted_says_nothing_and_fitted_copies_the_nearest(self):
        model = NearestNeighbourGenerativeModel()
        self.assertEqual(model.generate(TICKET, "", CAP.output_schema).confidence, 0.0)
        router, sink, t = make(model, policy=RoutingPolicy(0.3, stage="shadow"))
        for ticket in TicketGenerator(4).tickets(30):
            router.generate_state(ticket)
        examples, report = generative_examples_from_traces(sink.read(), CAP)
        self.assertEqual(report["examples"], 30)
        self.assertEqual(model.fit(examples), 30)
        seen = sink.traces[0].state
        assert sink.traces[0].generation is not None
        answer = model.generate(seen, "", CAP.output_schema)
        self.assertEqual(answer.output, sink.traces[0].generation.system2_output)
        self.assertGreater(answer.confidence, 0.99)
        self.assertLess(model.generate("entirely unrelated wording", "", CAP.output_schema).confidence, 0.15)

    def test_hash_mismatch_is_reported(self):
        router, sink, _ = make(None)
        router.generate_state(TICKET)
        edited = Capability(CAP.name, kind="generative", instructions=CAP.instructions + " Be brief.",
                            output_schema=CAP.output_schema)
        _, report = generative_examples_from_traces(sink.read(), edited)
        self.assertEqual(report["skipped_hash_mismatch"], 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
