"""Phase 1 exit gate, router half: a System-1 error, timeout or malformed answer never
fails the call; shadow records both answers; the trace path never raises into the caller."""
from __future__ import annotations

import random
import unittest
from typing import Mapping

from praxis.core.contracts import (
    Budget,
    Capability,
    DecisionResult,
    ModelInfo,
    Question,
    RequestContext,
    State,
    TeacherAnswer,
)
from praxis.core.router import DecisionRouter, RoutingPolicy, TeacherError
from praxis.providers.fake import MALFORMED_MODES, FakeCalibrator, FakeDecisionModel, FakeTeacher, FakeTraceSink
from tests.helpers import oracle, triage_capability

CAP = triage_capability()
TICKET = {"subject": "invoice charged twice",
          "body": "hi, why was I charged twice on the invoice. we need this today. we might switch providers."}
EXPECTED = {"department": "billing", "urgency": 2, "churn_risk": True}


def oracle_key(state: State, name: str, question: Question) -> str:
    return question.key_for(oracle(state, name, question))


def make(system1=None, *, policy=None, sink=None, calibrator=None, teacher=None, rng=None, on_trace_error=None):
    sink = sink if sink is not None else FakeTraceSink()
    teacher = teacher or FakeTeacher(oracle)
    router = DecisionRouter(CAP, teacher, system1, calibrator, sink, policy or RoutingPolicy(threshold=0.5),
                            rng=rng, on_trace_error=on_trace_error)
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
        router, sink, _ = make(FakeDecisionModel(delay_s=0.3), policy=RoutingPolicy(threshold=0.5, system1_timeout_ms=40))
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
                return {k: 0.7 for k in distribution}     # sums to 1.4 or 2.8: never a distribution
        router, sink, _ = make(FakeDecisionModel(peak=0.97), calibrator=BadCalibrator())
        self.assert_all_from_teacher(router.decide_state(TICKET), sink, "calibrator:")

    def test_no_system1_configured_is_an_abstention(self):
        router, sink, _ = make(None)
        self.assert_all_from_teacher(router.decide_state(TICKET), sink, "no system1")

    def test_a_hundred_hostile_calls_are_all_served_by_system2(self):
        hostile = [FakeDecisionModel(fail=ValueError("x")), FakeDecisionModel(malformed="nan"),
                   FakeDecisionModel(malformed="unknown-key"), FakeDecisionModel(delay_s=0.2),
                   FakeDecisionModel(malformed="not-a-mapping")]
        sink = FakeTraceSink()
        for i in range(100):
            router, _, _ = make(hostile[i % len(hostile)], sink=sink, policy=RoutingPolicy(0.5, system1_timeout_ms=20))
            results = router.decide_state(TICKET)
            self.assertEqual({r.answered_by for r in results.values()}, {"system2"})
        self.assertEqual(len(sink.traces), 100)
        self.assertTrue(all(t.abstain and t.success for t in sink.traces))


class ShadowRecordsBothAnswers(unittest.TestCase):
    def test_the_teacher_serves_and_system1_is_recorded_beside_it(self):
        wrong = FakeDecisionModel(pick=lambda s, n, q: q.keys()[-1], peak=0.9)   # always the last key
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

        router, _, _ = make(FakeDecisionModel(peak=0.97), sink=FakeTraceSink(fail=OSError("disk full")),
                            on_trace_error=hook)
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

    def test_score_results_carry_an_expected_value(self):
        router, _, _ = make(FakeDecisionModel(pick=oracle_key, peak=0.97))
        r = router.decide_state(TICKET)["urgency"]
        self.assertEqual(r.answer, 2)
        self.assertAlmostEqual(r.expected_value or 0.0, 2 * 0.97 + (0 + 1 + 3) * 0.01, places=9)

    def test_rank_is_derived_from_the_choice_distribution(self):
        cap = Capability("support.route", questions={"order": Question.rank("Order the teams by fit.",
                                                                            {"a": "A", "b": "B", "c": "C"})})
        model = FakeDecisionModel(pick=lambda s, n, q: "b", peak=0.8)
        seen: list[Question] = []

        class Spy(FakeDecisionModel):
            def decide(self, state, questions):
                seen.extend(questions.values())
                return model.decide(state, questions)

        router = DecisionRouter(cap, FakeTeacher(), Spy(), None, FakeTraceSink(), RoutingPolicy(0.1))
        r = router.decide_state("x")["order"]
        self.assertEqual(r.answer, ["b", "a", "c"])
        self.assertEqual(r.answered_by, "system1")
        self.assertEqual(seen[0].type, "choice", "the adapter sees the choice form")
        router = DecisionRouter(cap, FakeTeacher(), None, None, FakeTraceSink(), RoutingPolicy(0.1))
        r = router.decide_state("x")["order"]
        self.assertEqual(r.answer, ["a", "b", "c"])
        self.assertEqual(r.answered_by, "system2")

    def test_the_budget_caps_the_system1_timeout(self):
        router, sink, _ = make(FakeDecisionModel(delay_s=0.3), policy=RoutingPolicy(0.5, system1_timeout_ms=5_000))
        results = router.decide(CAP.request(TICKET, RequestContext(budget=Budget(max_latency_ms=30))))
        self.assertTrue(all(r.reason.startswith("timeout") for r in results.values()))

    def test_cost_is_summed_onto_the_trace(self):
        router, sink, _ = make(FakeDecisionModel(pick=oracle_key, peak=0.97, cost_usd=0.001))
        router.decide_state(TICKET)
        self.assertAlmostEqual(sink.traces[-1].cost_usd, 0.003)


class CanaryShare(unittest.TestCase):
    def test_share_zero_sends_every_call_to_the_teacher(self):
        router, _, teacher = make(FakeDecisionModel(pick=oracle_key, peak=0.97),
                                  policy=RoutingPolicy(0.5, stage="canary", canary_share=0.0))
        results = router.decide_state(TICKET)
        self.assertTrue(all(r.answered_by == "system2" and r.reason.startswith("canary") for r in results.values()))
        self.assertEqual(teacher.calls, 1)

    def test_share_one_behaves_like_serve(self):
        router, _, teacher = make(FakeDecisionModel(pick=oracle_key, peak=0.97),
                                  policy=RoutingPolicy(0.5, stage="canary", canary_share=1.0))
        self.assertTrue(all(r.answered_by == "system1" for r in router.decide_state(TICKET).values()))
        self.assertEqual(teacher.calls, 0)

    def test_a_half_share_splits_the_calls(self):
        router, _, _ = make(FakeDecisionModel(pick=oracle_key, peak=0.97),
                            policy=RoutingPolicy(0.5, stage="canary", canary_share=0.5), rng=random.Random(1))
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
                return {n: TeacherAnswer(oracle(state, n, q), {k: 0.7 for k in q.keys()}) for n, q in questions.items()}
        router, _, _ = make(None, teacher=Skewed())
        with self.assertRaises(TeacherError):
            router.decide_state(TICKET)

    def test_a_confident_system1_still_needs_no_teacher(self):
        router, _, _ = make(FakeDecisionModel(pick=oracle_key, peak=0.97), teacher=FakeTeacher(fail=RuntimeError("x")))
        self.assertTrue(all(r.answered_by == "system1" for r in router.decide_state(TICKET).values()))


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
        self.assertEqual(set(router.stats.as_dict()), {
            "calls", "questions", "system1_questions", "system2_questions", "system1_share", "abstain_reasons",
            "shadow_compared", "shadow_agreed", "shadow_agreement", "teacher_failures", "trace_failures"})

    def test_policies_are_validated(self):
        with self.assertRaises(ValueError):
            RoutingPolicy(threshold=1.5)
        with self.assertRaises(ValueError):
            RoutingPolicy(canary_share=-0.1)
        with self.assertRaises(ValueError):
            RoutingPolicy(system1_timeout_ms=0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
