"""Phase 1 exit gate, router half: a System-1 error, timeout or malformed answer never
fails the call; shadow records both answers; the trace path never raises into the caller."""

from __future__ import annotations

import random
import unittest
from collections.abc import Mapping

from praxis_core.contracts import (
    Budget,
    Capability,
    DecisionResult,
    ModelInfo,
    Question,
    RequestContext,
    State,
    TeacherAnswer,
    TraceEvent,
)
from praxis_core.providers.fake import MALFORMED_MODES, FakeCalibrator, FakeDecisionModel, FakeTeacher, FakeTraceSink
from praxis_core.router import DecisionRouter, RoutingPolicy, TeacherError
from tests.helpers import TicketGenerator, oracle, serving, triage_capability

CAP = triage_capability()
TICKET = {
    "subject": "invoice charged twice",
    "body": "hi, why was I charged twice on the invoice. we need this today. we might switch providers.",
}
EXPECTED = {"department": "billing", "urgency": 2, "churn_risk": True}


def oracle_key(state: State, name: str, question: Question) -> str:
    return question.key_for(oracle(state, name, question))


def make(system1=None, *, policy=None, sink=None, calibrator=None, teacher=None, rng=None, on_trace_error=None):
    sink = sink if sink is not None else FakeTraceSink()
    teacher = teacher or FakeTeacher(oracle)
    router = DecisionRouter(
        CAP,
        teacher,
        system1,
        calibrator,
        sink,
        policy or serving(),
        rng=rng,
        on_trace_error=on_trace_error,
    )
    return router, sink, teacher


class FaultInjectionNeverFailsTheCall(unittest.TestCase):
    def assert_all_from_teacher(self, results: Mapping[str, DecisionResult], sink: FakeTraceSink, prefix: str) -> None:
        self.assertEqual(set(results), set(CAP.questions))
        for name, r in results.items():
            self.assertEqual(r.answered_by, "system2", name)
            self.assertTrue(r.abstain, name)
            self.assertTrue(r.reason.startswith(prefix), f"{name}: {r.reason!r}")
            self.assertEqual(r.answer, EXPECTED[name])
        trace = sink.traces[-1]
        self.assertEqual(trace.answered_by, "system2")
        self.assertTrue(trace.abstain)
        self.assertTrue(trace.success)
        self.assertTrue(trace.label_candidate)
        for q in trace.questions:
            self.assertEqual(q.answered_by, "system2")
            self.assertIsNone(q.system1_answer)
            self.assertEqual(q.system2_answer, EXPECTED[q.name])

    def test_a_system1_error_is_an_abstention_with_a_reason(self):
        router, sink, _ = make(FakeDecisionModel(fail=RuntimeError("boom")))
        self.assert_all_from_teacher(router.decide_state(TICKET), sink, "error:")
        self.assertIn("boom", sink.traces[-1].system1_error or "")
        self.assertEqual(router.stats.abstain_reasons["error"], 3)

    def test_a_system1_timeout_is_an_abstention_with_a_reason(self):
        router, sink, _ = make(FakeDecisionModel(delay_s=0.3), policy=serving(system1_timeout_ms=40))
        self.assert_all_from_teacher(router.decide_state(TICKET), sink, "timeout:")
        self.assertLess(sink.traces[-1].system1_latency_ms or 0.0, 250.0)

    def test_every_malformed_answer_is_an_abstention_with_a_reason(self):
        for mode in MALFORMED_MODES:
            with self.subTest(mode=mode):
                router, sink, _ = make(FakeDecisionModel(malformed=mode))
                self.assert_all_from_teacher(router.decide_state(TICKET), sink, "malformed:")

    def test_a_misbehaving_calibrator_is_an_abstention_too(self):
        class BadCalibrator(FakeCalibrator):
            def apply(self, question, distribution):
                return {k: 0.7 for k in distribution}  # sums to 1.4 or 2.8: never a distribution

        router, sink, _ = make(FakeDecisionModel(peak=0.97), calibrator=BadCalibrator())
        self.assert_all_from_teacher(router.decide_state(TICKET), sink, "calibrator:")

    def test_no_system1_configured_is_an_abstention(self):
        router, sink, _ = make(None)
        self.assert_all_from_teacher(router.decide_state(TICKET), sink, "no system1")

    def test_a_hundred_hostile_calls_are_all_served_by_system2(self):
        hostile = [
            FakeDecisionModel(fail=ValueError("x")),
            FakeDecisionModel(malformed="nan"),
            FakeDecisionModel(malformed="unknown-key"),
            FakeDecisionModel(delay_s=0.2),
            FakeDecisionModel(malformed="not-a-mapping"),
        ]
        sink = FakeTraceSink()
        for i in range(100):
            router, _, _ = make(hostile[i % len(hostile)], sink=sink, policy=serving(system1_timeout_ms=20))
            results = router.decide_state(TICKET)
            self.assertEqual({r.answered_by for r in results.values()}, {"system2"})
        self.assertEqual(len(sink.traces), 100)
        self.assertTrue(all(t.abstain and t.success for t in sink.traces))


class ShadowRecordsBothAnswers(unittest.TestCase):
    def test_the_teacher_serves_and_system1_is_recorded_beside_it(self):
        wrong = FakeDecisionModel(pick=lambda s, n, q: q.keys()[-1], peak=0.9)  # always the last key
        router, sink, teacher = make(wrong, policy=RoutingPolicy(0.5, stage="shadow"))
        results = router.decide_state(TICKET)
        for name, r in results.items():
            self.assertEqual(r.answered_by, "system2")
            self.assertFalse(r.abstain, "shadow is not an abstention")
            self.assertEqual(r.answer, EXPECTED[name])
        trace = sink.traces[-1]
        self.assertEqual(trace.stage, "shadow")
        self.assertFalse(trace.abstain)
        self.assertTrue(trace.label_candidate)
        for q in trace.questions:
            self.assertIsNotNone(q.system1_answer)
            self.assertNotEqual(q.system1_answer, q.system2_answer)
            self.assertIsNotNone(q.raw_distribution)
            self.assertIsNotNone(q.calibrated_distribution)
            self.assertIsNotNone(q.confidence)
            self.assertEqual(q.native_confidence, 0.9)
            self.assertIn("shadow", q.reason)
        self.assertEqual(router.stats.shadow_compared, 3)
        self.assertEqual(router.stats.shadow_agreed, 0)
        self.assertEqual(teacher.calls, 1)

    def test_an_agreeing_model_scores_full_agreement(self):
        router, _, _ = make(FakeDecisionModel(pick=oracle_key), policy=RoutingPolicy(0.5, stage="shadow"))
        router.decide_state(TICKET)
        self.assertEqual(router.stats.as_dict()["shadow_agreement"], 1.0)

    def test_shadow_still_records_a_system1_failure(self):
        router, sink, _ = make(FakeDecisionModel(fail=RuntimeError("down")), policy=RoutingPolicy(0.5, stage="shadow"))
        results = router.decide_state(TICKET)
        self.assertEqual({r.answered_by for r in results.values()}, {"system2"})
        self.assertIn("down", sink.traces[-1].system1_error or "")
        self.assertEqual(router.stats.shadow_compared, 0)


class TheTracePathNeverRaises(unittest.TestCase):
    def test_a_failing_sink_is_counted_not_raised(self):
        router, _, _ = make(FakeDecisionModel(peak=0.97), sink=FakeTraceSink(fail=RuntimeError("disk full")))
        results = router.decide_state(TICKET)
        self.assertEqual(set(results), set(CAP.questions))
        self.assertEqual(router.stats.trace_failures, 1)

    def test_the_hook_sees_the_error_and_a_failing_hook_is_swallowed_too(self):
        seen: list[BaseException] = []

        def hook(exc: BaseException) -> None:
            seen.append(exc)
            raise RuntimeError("the hook is broken as well")

        router, _, _ = make(
            FakeDecisionModel(peak=0.97), sink=FakeTraceSink(fail=OSError("disk full")), on_trace_error=hook
        )
        router.decide_state(TICKET)
        self.assertEqual(len(seen), 1)
        self.assertIsInstance(seen[0], OSError)


class ServeAndAbstain(unittest.TestCase):
    def test_confident_and_valid_is_served_by_system1(self):
        router, sink, teacher = make(FakeDecisionModel(pick=oracle_key, peak=0.97))
        results = router.decide_state(TICKET)
        for name, r in results.items():
            self.assertEqual(r.answered_by, "system1")
            self.assertFalse(r.abstain)
            self.assertEqual(r.answer, EXPECTED[name])
            self.assertEqual((r.provider, r.model), ("fake", "fake-system1"))
        self.assertEqual(teacher.calls, 0)
        self.assertEqual(sink.traces[-1].answered_by, "system1")
        self.assertFalse(sink.traces[-1].label_candidate)

    def test_below_threshold_abstains_and_says_so(self):
        router, sink, teacher = make(FakeDecisionModel(pick=oracle_key, peak=0.4))
        results = router.decide_state(TICKET)
        for r in results.values():
            self.assertEqual(r.answered_by, "system2")
            self.assertTrue(r.abstain)
            self.assertTrue(r.reason.startswith("below threshold"), r.reason)
        self.assertEqual(teacher.calls, 1)
        self.assertTrue(sink.traces[-1].label_candidate)
        self.assertEqual(sink.traces[-1].question("urgency").system1_answer, 2)

    def test_a_partial_abstain_asks_the_teacher_only_the_abstaining_question(self):
        model = FakeDecisionModel(pick=oracle_key, peak={"department": 0.97, "urgency": 0.3, "churn_risk": 0.97})
        router, sink, teacher = make(model)
        results = router.decide_state(TICKET)
        self.assertEqual(results["department"].answered_by, "system1")
        self.assertEqual(results["churn_risk"].answered_by, "system1")
        self.assertEqual(results["urgency"].answered_by, "system2")
        self.assertTrue(results["urgency"].abstain)
        self.assertEqual(teacher.questions_answered, 1)
        trace = sink.traces[-1]
        self.assertTrue(trace.abstain)
        self.assertEqual(trace.answered_by, "system2")
        self.assertEqual(trace.question("department").answered_by, "system1")
        self.assertIsNone(trace.question("department").system2_answer)

    def test_the_calibrated_flag_reflects_the_calibrator(self):
        router, sink, _ = make(FakeDecisionModel(pick=oracle_key, peak=0.97), calibrator=FakeCalibrator(fitted=True))
        r = router.decide_state(TICKET)["department"]
        self.assertTrue(r.calibrated)
        self.assertEqual(sink.traces[-1].question("department").calibrator_version, "fake-calibrator")
        router, sink, _ = make(FakeDecisionModel(pick=oracle_key, peak=0.97), calibrator=FakeCalibrator(fitted=False))
        self.assertFalse(router.decide_state(TICKET)["department"].calibrated)
        self.assertIsNone(sink.traces[-1].question("department").calibrator_version)
        router, _, _ = make(FakeDecisionModel(pick=oracle_key, peak=0.97))
        self.assertFalse(router.decide_state(TICKET)["department"].calibrated)

    def test_require_calibrated_refuses_an_uncalibrated_question(self):
        model = FakeDecisionModel(pick=oracle_key, peak=0.97)
        router, _, _ = make(model, calibrator=FakeCalibrator(fitted=False), policy=serving(require_calibrated=True))
        results = router.decide_state(TICKET)
        self.assertTrue(
            all(r.answered_by == "system2" and r.reason.startswith("uncalibrated") for r in results.values())
        )
        router, _, _ = make(model, calibrator=FakeCalibrator(fitted=True), policy=serving(require_calibrated=True))
        self.assertTrue(all(r.answered_by == "system1" for r in router.decide_state(TICKET).values()))

    def test_score_results_carry_an_expected_value(self):
        router, _, _ = make(FakeDecisionModel(pick=oracle_key, peak=0.97))
        r = router.decide_state(TICKET)["urgency"]
        self.assertEqual(r.answer, 2)
        self.assertAlmostEqual(r.expected_value or 0.0, 2 * 0.97 + (0 + 1 + 3) * 0.01, places=9)

    def test_rank_is_derived_from_the_choice_distribution(self):
        cap = Capability(
            "support.route",
            questions={"order": Question.rank("Order the teams by fit.", {"a": "A", "b": "B", "c": "C"})},
        )
        model = FakeDecisionModel(pick=lambda s, n, q: "b", peak=0.8)
        seen: list[Question] = []

        class Spy(FakeDecisionModel):
            def decide(self, state, questions):
                seen.extend(questions.values())
                return model.decide(state, questions)

        router = DecisionRouter(cap, FakeTeacher(), Spy(), None, FakeTraceSink(), serving(0.1))
        r = router.decide_state("x")["order"]
        self.assertEqual(r.answer, ["b", "a", "c"])
        self.assertEqual(r.answered_by, "system1")
        self.assertEqual(seen[0].type, "choice", "the adapter sees the choice form")
        router = DecisionRouter(cap, FakeTeacher(), None, None, FakeTraceSink(), serving(0.1))
        r = router.decide_state("x")["order"]
        self.assertEqual(r.answer, ["a", "b", "c"])
        self.assertEqual(r.answered_by, "system2")

    def test_the_budget_caps_the_system1_timeout(self):
        router, sink, _ = make(FakeDecisionModel(delay_s=0.3), policy=serving(system1_timeout_ms=5_000))
        results = router.decide(CAP.request(TICKET, RequestContext(budget=Budget(max_latency_ms=30))))
        self.assertTrue(all(r.reason.startswith("timeout") for r in results.values()))

    def test_cost_is_summed_onto_the_trace(self):
        router, sink, _ = make(FakeDecisionModel(pick=oracle_key, peak=0.97, cost_usd=0.001))
        router.decide_state(TICKET)
        self.assertAlmostEqual(sink.traces[-1].cost_usd, 0.003)


class CanaryShare(unittest.TestCase):
    def test_share_zero_sends_every_call_to_the_teacher(self):
        router, _, teacher = make(
            FakeDecisionModel(pick=oracle_key, peak=0.97), policy=serving(stage="canary", canary_share=0.0)
        )
        results = router.decide_state(TICKET)
        self.assertTrue(all(r.answered_by == "system2" and r.reason.startswith("canary") for r in results.values()))
        self.assertEqual(teacher.calls, 1)

    def test_share_one_behaves_like_serve(self):
        router, _, teacher = make(
            FakeDecisionModel(pick=oracle_key, peak=0.97), policy=serving(stage="canary", canary_share=1.0)
        )
        self.assertTrue(all(r.answered_by == "system1" for r in router.decide_state(TICKET).values()))
        self.assertEqual(teacher.calls, 0)

    def test_a_half_share_splits_the_calls(self):
        router, _, _ = make(
            FakeDecisionModel(pick=oracle_key, peak=0.97),
            policy=serving(stage="canary", canary_share=0.5),
            rng=random.Random(1),
        )
        for _ in range(40):
            router.decide_state(TICKET)
        stats = router.stats.as_dict()
        self.assertGreater(stats["system1_questions"], 0)
        self.assertGreater(stats["system2_questions"], 0)
        self.assertEqual(stats["system1_questions"] + stats["system2_questions"], 120)
        self.assertIn("canary", stats["abstain_reasons"])


class TheTeacherIsTheOnlyThingThatCanFail(unittest.TestCase):
    def test_a_teacher_exception_is_recorded_then_raised(self):
        sink = FakeTraceSink()
        router, _, _ = make(None, sink=sink, teacher=FakeTeacher(fail=RuntimeError("boom")))
        with self.assertRaises(TeacherError):
            router.decide_state(TICKET)
        trace = sink.traces[-1]
        self.assertFalse(trace.success)
        self.assertIn("boom", trace.error_message or "")
        self.assertFalse(trace.label_candidate)
        self.assertEqual(router.stats.teacher_failures, 1)

    def test_a_teacher_answer_outside_the_declared_set_is_a_teacher_error(self):
        def liar(state, name, question):
            return "nonsense" if name == "department" else oracle(state, name, question)

        router, sink, _ = make(None, teacher=FakeTeacher(liar))
        with self.assertRaises(TeacherError):
            router.decide_state(TICKET)
        self.assertIn("declared set", sink.traces[-1].error_message or "")

    def test_a_teacher_distribution_that_does_not_sum_to_one_is_a_teacher_error(self):
        class Skewed:
            info = ModelInfo("fake", "skewed")

            def answer(self, state, questions):
                return {
                    n: TeacherAnswer(oracle(state, n, q), {k: 0.7 for k in q.keys()})  # noqa: SIM118 - a method
                    for n, q in questions.items()
                }

        router, _, _ = make(None, teacher=Skewed())
        with self.assertRaises(TeacherError):
            router.decide_state(TICKET)

    def test_a_confident_system1_still_needs_no_teacher(self):
        router, _, _ = make(FakeDecisionModel(pick=oracle_key, peak=0.97), teacher=FakeTeacher(fail=RuntimeError("x")))
        self.assertTrue(all(r.answered_by == "system1" for r in router.decide_state(TICKET).values()))


class TheDefaultPolicyIsSafe(unittest.TestCase):
    """PX-900. A router built with no policy shadows and serves nothing uncalibrated; the
    README's "nothing is served uncalibrated" is the default, not an option."""

    def test_the_defaults_are_shadow_and_calibration_required(self):
        policy = RoutingPolicy()
        self.assertEqual(policy.stage, "shadow")
        self.assertTrue(policy.require_calibrated)

    def test_a_router_with_no_policy_never_serves_an_uncalibrated_student(self):
        sure = FakeDecisionModel(pick=oracle_key, peak=1.0)  # always certain, never calibrated
        sink = FakeTraceSink()
        router = DecisionRouter(CAP, FakeTeacher(oracle), sure, None, sink)
        results = router.decide_state(TICKET)
        self.assertTrue(all(r.answered_by == "system2" for r in results.values()), "shadow by default")
        self.assertTrue(all(q.system1_answer is not None for q in sink.traces[-1].questions), "but recorded")
        router.set_policy(RoutingPolicy(stage="serve"))  # the stage alone is not enough
        results = router.decide_state(TICKET)
        self.assertTrue(
            all(r.answered_by == "system2" and r.reason.startswith("uncalibrated") for r in results.values())
        )
        fitted = DecisionRouter(CAP, FakeTeacher(oracle), sure, FakeCalibrator(fitted=True), sink)
        fitted.set_policy(RoutingPolicy(stage="serve"))
        self.assertTrue(all(r.answered_by == "system1" for r in fitted.decide_state(TICKET).values()))


class RequestsAreCheckedAgainstTheCapability(unittest.TestCase):
    def test_the_wrong_capability_is_a_caller_error(self):
        router, _, _ = make(None)
        other = Capability("support.other", questions=CAP.questions)
        with self.assertRaises(ValueError):
            router.decide(other.request(TICKET))

    def test_a_missing_or_retyped_question_is_a_caller_error(self):
        router, _, _ = make(None)
        with self.assertRaises(ValueError):
            router.decide(CAP.request(TICKET, questions={"department": CAP.questions["department"]}))
        retyped = dict(CAP.questions, urgency=Question.boolean("Urgent?"))
        with self.assertRaises(ValueError):
            router.decide(CAP.request(TICKET, questions=retyped))

    def test_dynamic_options_are_allowed_and_hashed_as_presented(self):
        router, sink, _ = make(FakeDecisionModel(pick=oracle_key, peak=0.97))
        narrowed = dict(CAP.questions, department=Question.choice("Which team?", {"billing": "B", "technical": "T"}))
        r = router.decide(CAP.request(TICKET, questions=narrowed))["department"]
        self.assertEqual(set(r.distribution), {"billing", "technical"})
        q = sink.traces[-1].question("department")
        self.assertNotEqual(q.options_or_levels_hash, CAP.questions["department"].definition_hash)
        self.assertEqual(q.question.options, {"billing": "B", "technical": "T"})


class StatsHaveAStableShape(unittest.TestCase):
    def test_as_dict_keys(self):
        router, _, _ = make(FakeDecisionModel(pick=oracle_key, peak=0.97))
        router.decide_state(TICKET)
        self.assertEqual(
            set(router.stats.as_dict()),
            {
                "calls",
                "questions",
                "system1_questions",
                "system2_questions",
                "system1_share",
                "abstain_reasons",
                "shadow_compared",
                "shadow_agreed",
                "shadow_agreement",
                "teacher_failures",
                "trace_failures",
                "observed",
                "observe_failures",
            },
        )

    def test_policies_are_validated(self):
        with self.assertRaises(ValueError):
            RoutingPolicy(threshold=1.5)
        with self.assertRaises(ValueError):
            RoutingPolicy(canary_share=-0.1)
        with self.assertRaises(ValueError):
            RoutingPolicy(system1_timeout_ms=0)


class ObserveModeNeverTouchesTheRequestPath(unittest.TestCase):
    """PX-100: the app's own answer becomes the trace; the student runs in shadow; nothing raises."""

    APP = ModelInfo("app", "the-apps-own-model", "2026-10")

    def test_the_apps_answer_is_recorded_as_system2_and_the_student_in_shadow(self):
        router, sink, teacher = make(FakeDecisionModel(pick=lambda s, n, q: q.keys()[-1], peak=0.9))
        trace = router.observe_state(TICKET, EXPECTED, self.APP, latency_ms=812.0, cost_usd=0.004)
        self.assertIsNotNone(trace)
        assert trace is not None
        self.assertEqual(trace.mode, "observe")
        self.assertTrue(trace.success)
        self.assertTrue(trace.label_candidate)
        self.assertEqual(trace.system2, self.APP)
        self.assertEqual(trace.system2_latency_ms, 812.0)
        self.assertEqual(trace.cost_usd, 0.004)
        self.assertEqual(teacher.calls, 0, "Praxis never called a teacher; the app did")
        for q in trace.questions:
            self.assertEqual(q.answered_by, "system2")
            self.assertFalse(q.abstain)
            self.assertEqual(q.system2_answer, EXPECTED[q.name])
            self.assertIsNotNone(q.system1_answer, "the student ran in shadow")
            self.assertIn("observe", q.reason)
        self.assertEqual(sink.traces[-1], trace)
        self.assertEqual(router.stats.observed, 1)
        self.assertEqual(router.stats.shadow_compared, 3)

    def test_replay_equivalence_the_trace_rebuilds_the_request(self):
        router, sink, _ = make(None)
        request = CAP.request(TICKET, RequestContext(host_partition="tenant-a", caller="checkout-service"))
        trace = router.observe(request, EXPECTED, self.APP)
        assert trace is not None
        again = TraceEvent.from_json(trace.to_json()).to_request()
        self.assertEqual(again.capability, request.capability)
        self.assertEqual(again.state, request.state)
        self.assertEqual(again.questions, request.questions)
        self.assertEqual(again.context.host_partition, "tenant-a")
        self.assertEqual(again.context.caller, "checkout-service")
        narrowed = dict(CAP.questions, department=Question.choice("Which team?", {"billing": "B", "technical": "T"}))
        trace2 = router.observe(CAP.request(TICKET, questions=narrowed), EXPECTED, self.APP)
        assert trace2 is not None
        self.assertEqual(trace2.to_request().questions["department"].options, {"billing": "B", "technical": "T"})

    def test_an_invalid_answer_is_a_recorded_failure_not_a_label(self):
        router, sink, _ = make(None)
        trace = router.observe_state(TICKET, {"department": "nonsense", "urgency": 2, "churn_risk": True}, self.APP)
        assert trace is not None
        self.assertFalse(trace.success)
        self.assertFalse(trace.label_candidate)
        self.assertIn("declared set", trace.error_message or "")
        self.assertEqual(len(sink.traces), 1)
        missing = router.observe_state(TICKET, {"department": "billing"}, self.APP)
        assert missing is not None
        self.assertFalse(missing.success)
        self.assertIn("no answer for", missing.error_message or "")

    def test_a_bad_request_is_recorded_and_nothing_raises(self):
        router, sink, _ = make(None)
        other = Capability("support.other", questions=CAP.questions)
        trace = router.observe(other.request(TICKET), EXPECTED, self.APP)
        assert trace is not None
        self.assertFalse(trace.success)
        self.assertIn("this router serves", trace.error_message or "")
        self.assertEqual(trace.questions, [])

    def test_nothing_the_app_passes_can_raise(self):
        router, _, _ = make(FakeDecisionModel(malformed="nan"), sink=FakeTraceSink(fail=RuntimeError("disk full")))
        for answers in (EXPECTED, {}, {"department": object()}, {"urgency": "high"}, None):  # type: ignore[list-item]
            trace = router.observe_state(TICKET, answers or {}, self.APP)
            self.assertTrue(trace is None or trace.mode == "observe")
        self.assertEqual(router.stats.observe_failures, 0, "every case was handled, none escaped")
        self.assertGreaterEqual(router.stats.trace_failures, 1, "the dead sink was counted")

    def test_observed_traces_become_examples_and_fit_the_student(self):
        from praxis_core.baseline import NearestNeighbourDecisionModel
        from praxis_core.dataset import examples_from_traces

        router, sink, teacher = make(None)
        for ticket in TicketGenerator(3).tickets(20):
            answers = {n: a.answer for n, a in teacher.answer(ticket, CAP.questions).items()}
            router.observe_state(ticket, answers, self.APP)
        examples, report = examples_from_traces(sink.read(), CAP)
        self.assertEqual(report["examples"], 60)
        student = NearestNeighbourDecisionModel()
        self.assertEqual(student.fit(examples), 60)


if __name__ == "__main__":
    unittest.main(verbosity=2)
