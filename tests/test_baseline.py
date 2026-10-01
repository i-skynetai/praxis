"""The nearest-neighbour student, migrated to the DecisionModel port: unfitted it says
nothing (uniform, never served), fitted it answers what it has seen, and the loop from
shadow traces to a fitted student closes without anything installed."""

from __future__ import annotations

import unittest

from praxis_core.baseline import NearestNeighbourDecisionModel, jaccard, tokens
from praxis_core.confidence import argmax, confidence
from praxis_core.contracts import Capability, Question
from praxis_core.dataset import examples_from_traces
from praxis_core.ports import DecisionModel
from praxis_core.providers.fake import FakeTeacher, FakeTraceSink
from praxis_core.router import DecisionRouter, RoutingPolicy
from tests.helpers import TicketGenerator, oracle, triage_capability

CAP = triage_capability()


def shadow_traces(n: int, seed: int = 1) -> tuple[FakeTraceSink, TicketGenerator]:
    sink = FakeTraceSink()
    router = DecisionRouter(
        CAP, FakeTeacher(oracle), NearestNeighbourDecisionModel(), None, sink, RoutingPolicy(0.5, stage="shadow")
    )
    generator = TicketGenerator(seed)
    for ticket in generator.tickets(n):
        router.decide_state(ticket)
    return sink, generator


class TheBaselineIsADecisionModel(unittest.TestCase):
    def test_it_satisfies_the_port(self):
        self.assertIsInstance(NearestNeighbourDecisionModel(), DecisionModel)
        self.assertEqual(NearestNeighbourDecisionModel().info.model, "nearest-neighbour")

    def test_unfitted_it_is_uniform_and_the_router_never_serves_it(self):
        model = NearestNeighbourDecisionModel()
        self.assertFalse(model.fitted)
        raw = model.decide({"subject": "x"}, CAP.questions)
        for name, answer in raw.items():
            self.assertEqual(confidence(answer.distribution), 0.0, name)
            self.assertEqual(answer.native_confidence, 0.0)
        router = DecisionRouter(CAP, FakeTeacher(oracle), model, None, FakeTraceSink(), RoutingPolicy(threshold=0.01))
        results = router.decide_state({"subject": "invoice charged twice"})
        self.assertTrue(
            all(r.answered_by == "system2" and r.reason.startswith("below threshold") for r in results.values())
        )

    def test_it_answers_something_it_has_seen(self):
        sink, _ = shadow_traces(40)
        examples, report = examples_from_traces(sink.read(), CAP)
        self.assertEqual(report["examples"], 120)
        self.assertEqual(report["skipped_hash_mismatch"], 0)
        model = NearestNeighbourDecisionModel()
        self.assertEqual(model.fit(examples), 120)
        seen = sink.traces[0]
        raw = model.decide(seen.state, CAP.questions)
        for q in seen.questions:
            keys = q.question.keys()
            label = q.question.key_for(q.system2_answer)
            self.assertEqual(argmax(raw[q.name].distribution, keys), label, q.name)
            self.assertGreater(raw[q.name].distribution[label], 0.5, "the remembered answer holds a majority")
            self.assertGreater(raw[q.name].native_confidence or 0.0, 0.99, "an exact match is remembered as such")
            self.assertGreater(confidence(raw[q.name].distribution), 0.2)

    def test_it_is_unsure_about_something_unrelated(self):
        sink, _ = shadow_traces(40)
        model = NearestNeighbourDecisionModel()
        model.fit(examples_from_traces(sink.read(), CAP)[0])
        raw = model.decide("entirely unrelated wording here", CAP.questions)
        self.assertLess(max(raw["department"].distribution.values()), 0.4)
        self.assertIsNotNone(raw["department"].native_confidence)
        self.assertLess(raw["department"].native_confidence or 0.0, 0.15)
        self.assertLess(confidence(raw["department"].distribution), 0.1)

    def test_dynamic_options_only_count_votes_for_the_keys_presented(self):
        sink, _ = shadow_traces(40)
        model = NearestNeighbourDecisionModel()
        model.fit(examples_from_traces(sink.read(), CAP)[0])
        narrowed = {"department": Question.choice("Which team?", {"account": "A", "sales": "S"})}
        billing_ticket = next(t.state for t in sink.traces if t.question("department").system2_answer == "billing")
        raw = model.decide(billing_ticket, narrowed)["department"]
        self.assertEqual(set(raw.distribution), {"account", "sales"})
        self.assertAlmostEqual(sum(raw.distribution.values()), 1.0)

    def test_from_shadow_traces_to_a_serving_student_closes_the_loop(self):
        sink, generator = shadow_traces(60)
        model = NearestNeighbourDecisionModel()
        model.fit(examples_from_traces(sink.read(), CAP)[0])
        router = DecisionRouter(CAP, FakeTeacher(oracle), model, None, FakeTraceSink(), RoutingPolicy(threshold=0.3))
        for ticket in generator.tickets(60):
            router.decide_state(ticket)
        stats = router.stats.as_dict()
        self.assertGreater(stats["system1_questions"], 0, "a fitted student serves something")
        self.assertGreater(stats["system2_questions"], 0, "and abstains on the rest")

    def test_a_silently_edited_option_list_is_reported_not_learned(self):
        sink, _ = shadow_traces(10)
        edited = Capability(
            CAP.name,
            questions=dict(
                CAP.questions,
                department=Question.choice(
                    "Which team?", {**CAP.questions["department"].options, "sales": "Pricing (edited)"}
                ),
            ),
        )
        examples, report = examples_from_traces(sink.read(), edited)
        self.assertEqual(report["skipped_hash_mismatch"], 10)
        self.assertEqual(report["examples"], 20)
        self.assertTrue(all(e.question_name != "department" for e in examples))

    def test_traces_that_were_not_label_candidates_are_skipped(self):
        sink = FakeTraceSink()
        router = DecisionRouter(CAP, FakeTeacher(oracle), None, None, sink, RoutingPolicy(0.5))
        router.decide_state({"subject": "x"})
        sink.traces[0].label_candidate = False
        _, report = examples_from_traces(sink.read(), CAP)
        self.assertEqual(report["skipped_not_label_candidate"], 1)
        self.assertEqual(report["examples"], 0)


class TokensAndSimilarity(unittest.TestCase):
    def test_tokens_are_lowercase_words_from_strings_and_dicts(self):
        self.assertEqual(tokens("Hi, Login Page!"), frozenset({"hi", "login", "page"}))
        self.assertIn("broken", tokens({"text": "Login broken"}))

    def test_jaccard(self):
        self.assertEqual(jaccard(frozenset("ab"), frozenset("ab")), 1.0)
        self.assertEqual(jaccard(frozenset("ab"), frozenset("cd")), 0.0)
        self.assertEqual(jaccard(frozenset(), frozenset()), 0.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
