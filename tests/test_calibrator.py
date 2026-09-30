"""The temperature calibrator: one temperature per (question type, option count), fitted
on traces that carry both a raw System-1 distribution and a System-2 label."""
from __future__ import annotations

import math
import random
import unittest

from praxis.core.calibrate import (
    TemperatureCalibrator,
    expected_calibration_error,
    negative_log_likelihood,
    scale,
)
from praxis.core.confidence import argmax, confidence
from praxis.core.contracts import Question, QuestionTrace, TraceEvent
from praxis.core.ports import Calibrator
from tests.helpers import triage_capability

CAP = triage_capability()


def synthetic(rng: random.Random, question: Question, n: int, true_temperature: float,
              name: str = "q") -> list[TraceEvent]:
    """Traces where the model's raw distribution is the truth sharpened or softened by
    ``true_temperature``; the label is drawn from the truth."""
    keys = question.as_choice().keys()
    traces: list[TraceEvent] = []
    for i in range(n):
        weights = [math.exp(rng.gauss(0.0, 1.5)) for _ in keys]
        truth = {k: w / sum(weights) for k, w in zip(keys, weights)}
        label = rng.choices(keys, weights=[truth[k] for k in keys])[0]
        raw = scale(truth, keys, true_temperature)
        traces.append(TraceEvent(
            trace_id=f"{name}-{i}", capability=CAP.name, capability_kind="decision", capability_hash="h",
            stage="shadow", answered_by="system2", abstain=False, state=f"state {i}",
            questions=[QuestionTrace(name, question.type, question.definition_hash, question, "system2", False,
                                     raw_distribution=raw, system2_answer=question.answer_for(label))],
            label_candidate=True))
    return traces


def reliability(traces: list[TraceEvent], calibrator: TemperatureCalibrator | None) -> tuple[float, float]:
    """(negative log-likelihood, expected calibration error) of the argmax over the traces."""
    items, keys_of, max_ps, corrects = [], [], [], []
    for t in traces:
        q = t.questions[0]
        question = q.question.as_choice()
        keys = question.keys()
        assert q.raw_distribution is not None and q.system2_answer is not None
        label = question.key_for(q.system2_answer)
        applied = calibrator.apply(question, q.raw_distribution) if calibrator else dict(q.raw_distribution)
        items.append((applied, label))
        keys_of.append(keys)
        top = argmax(applied, keys)
        max_ps.append(applied[top])
        corrects.append(top == label)
    return negative_log_likelihood(items, keys_of, 1.0), expected_calibration_error(max_ps, corrects)


class TemperatureIsFittedPerTypeAndOptionCount(unittest.TestCase):
    def test_an_over_confident_model_gets_a_temperature_above_one(self):
        rng = random.Random(3)
        train = synthetic(rng, CAP.questions["department"], 400, 0.4)
        held = synthetic(rng, CAP.questions["department"], 400, 0.4)
        cal = TemperatureCalibrator()
        params = cal.fit(train)
        self.assertEqual(set(params), {"choice/4"})
        self.assertGreater(params["choice/4"], 1.8)
        self.assertLess(params["choice/4"], 3.5)
        nll_before, ece_before = reliability(held, None)
        nll_after, ece_after = reliability(held, cal)
        self.assertLess(nll_after, nll_before)
        self.assertLess(ece_after, ece_before)

    def test_an_under_confident_model_gets_a_temperature_below_one(self):
        rng = random.Random(4)
        train = synthetic(rng, CAP.questions["urgency"], 400, 2.5)
        cal = TemperatureCalibrator()
        params = cal.fit(train)
        self.assertEqual(set(params), {"score/4"})
        self.assertGreater(params["score/4"], 0.25)
        self.assertLess(params["score/4"], 0.6)
        raw = {"0": 0.3, "1": 0.3, "2": 0.25, "3": 0.15}
        self.assertGreater(confidence(cal.apply(CAP.questions["urgency"], raw)), confidence(raw))

    def test_groups_are_independent_and_small_groups_are_reported(self):
        rng = random.Random(5)
        traces = (synthetic(rng, CAP.questions["department"], 60, 0.5, "c")
                  + synthetic(rng, CAP.questions["churn_risk"], 60, 0.5, "b")
                  + synthetic(rng, CAP.questions["urgency"], 4, 0.5, "s"))
        cal = TemperatureCalibrator(min_examples=10)
        params = cal.fit(traces)
        self.assertEqual(set(params), {"choice/4", "boolean/2"})
        self.assertTrue(cal.is_fitted(CAP.questions["department"]))
        self.assertTrue(cal.is_fitted(CAP.questions["churn_risk"]))
        self.assertFalse(cal.is_fitted(CAP.questions["urgency"]))
        self.assertEqual(cal.skipped, {"score/4": 4})
        untouched = {"0": 0.7, "1": 0.1, "2": 0.1, "3": 0.1}
        self.assertEqual(cal.apply(CAP.questions["urgency"], untouched), untouched)

    def test_the_same_option_count_across_types_is_two_groups(self):
        rng = random.Random(6)
        four_way = Question.choice("c", {"a": "A", "b": "B", "c": "C", "d": "D"})
        cal = TemperatureCalibrator()
        cal.fit(synthetic(rng, four_way, 60, 0.4))
        self.assertTrue(cal.is_fitted(four_way))
        self.assertFalse(cal.is_fitted(CAP.questions["urgency"]), "score/4 is not choice/4")

    def test_rank_traces_fit_the_choice_group(self):
        rng = random.Random(7)
        ranked = Question.rank("r", {"a": "A", "b": "B", "c": "C"})
        traces = synthetic(rng, ranked, 60, 0.4)
        for t in traces:
            q = t.questions[0]
            assert q.raw_distribution is not None and isinstance(q.system2_answer, str)
            top = q.system2_answer
            q.system2_answer = [top] + [k for k in ranked.keys() if k != top]
        cal = TemperatureCalibrator()
        self.assertEqual(set(cal.fit(traces)), {"choice/3"})
        self.assertTrue(cal.is_fitted(ranked))

    def test_unfitted_apply_is_the_identity(self):
        cal = TemperatureCalibrator()
        raw = {"true": 0.8, "false": 0.2}
        self.assertEqual(cal.apply(CAP.questions["churn_risk"], raw), raw)
        self.assertEqual(cal.version, "temperature-v1/unfitted")

    def test_parameters_round_trip_and_the_version_follows_the_fit(self):
        rng = random.Random(8)
        cal = TemperatureCalibrator()
        before = cal.version
        cal.fit(synthetic(rng, CAP.questions["department"], 60, 0.5))
        self.assertNotEqual(cal.version, before)
        again = TemperatureCalibrator.from_dict(cal.to_dict())
        self.assertEqual(again.version, cal.version)
        raw = {"billing": 0.6, "technical": 0.2, "account": 0.1, "sales": 0.1}
        self.assertEqual(again.apply(CAP.questions["department"], raw), cal.apply(CAP.questions["department"], raw))

    def test_it_satisfies_the_port(self):
        self.assertIsInstance(TemperatureCalibrator(), Calibrator)


class ExpectedCalibrationError(unittest.TestCase):
    def test_a_perfectly_calibrated_model_scores_near_zero(self):
        rng = random.Random(9)
        probs = [rng.uniform(0.5, 1.0) for _ in range(5000)]
        corrects = [rng.random() < p for p in probs]
        self.assertLess(expected_calibration_error(probs, corrects), 0.03)

    def test_an_over_confident_model_scores_high(self):
        self.assertGreater(expected_calibration_error([0.95] * 100, [i % 2 == 0 for i in range(100)]), 0.4)

    def test_lengths_must_match(self):
        with self.assertRaises(ValueError):
            expected_calibration_error([0.5], [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
