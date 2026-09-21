import os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from praxis.seam import Capability, Trace, call_teacher
from praxis.gate import Gate
from praxis.student import NearestNeighbourStudent, LoraStudent
from praxis.router import Router
from praxis.evaluate import evaluate, split, table

CAP = Capability("classify", "Classify the ticket.", {"label": "str"})
DATA = [("login page broken", "bug"), ("add dark mode", "feature"),
        ("crash on save", "bug"), ("export to csv", "feature"),
        ("500 on upload", "bug"), ("bulk edit please", "feature")]


def traced(gate=None):
    g = gate or Gate(CAP)
    return [g.judge(Trace("classify", {"text": t}, {"label": l}, "teacher", 5)) for t, l in DATA]


class TheSeamIsTyped(unittest.TestCase):
    def test_a_valid_output_passes(self):
        self.assertTrue(CAP.validate({"label": "bug"})[0])

    def test_a_missing_field_fails_with_a_reason(self):
        ok, why = CAP.validate({})
        self.assertFalse(ok); self.assertIn("missing field", why)

    def test_an_extra_field_fails(self):
        ok, why = CAP.validate({"label": "bug", "smuggled": 1})
        self.assertFalse(ok); self.assertIn("unexpected", why)

    def test_calling_the_teacher_records_a_trace(self):
        t = call_teacher(CAP, {"text": "x"}, lambda p: {"label": "bug"})
        self.assertEqual(t.capability, "classify")
        self.assertEqual(t.output, {"label": "bug"})


class TheGateRejectsAndSaysWhy(unittest.TestCase):
    def test_malformed_output_is_rejected(self):
        t = Gate(CAP).judge(Trace("classify", {"a": 1}, {"nope": 1}, "m", 5))
        self.assertFalse(t.accepted); self.assertIn("schema", t.reason)

    def test_a_duplicate_input_is_rejected_once_seen(self):
        g = Gate(CAP)
        g.judge(Trace("classify", {"a": 1}, {"label": "bug"}, "m", 5))
        again = g.judge(Trace("classify", {"a": 1}, {"label": "bug"}, "m", 5))
        self.assertFalse(again.accepted); self.assertIn("duplicate", again.reason)

    def test_a_slow_trace_is_rejected(self):
        g = Gate(CAP, max_latency_ms=100)
        t = g.judge(Trace("classify", {"a": 1}, {"label": "bug"}, "m", 5000))
        self.assertFalse(t.accepted); self.assertIn("slow", t.reason)

    def test_the_report_counts_by_reason(self):
        g = Gate(CAP); traced(g)
        g.judge(Trace("classify", {"z": 1}, {"bad": 1}, "m", 5))
        self.assertEqual(g.report()["by_reason"]["schema"], 1)


class TheStudentLearnsFromAcceptedTracesOnly(unittest.TestCase):
    def test_it_answers_something_it_has_seen(self):
        s = NearestNeighbourStudent(); s.fit(traced())
        out, conf = s.predict({"text": "login page broken"})
        self.assertEqual(out, {"label": "bug"}); self.assertGreater(conf, 0.9)

    def test_it_is_unsure_about_something_unrelated(self):
        s = NearestNeighbourStudent(); s.fit(traced())
        _, conf = s.predict({"text": "entirely unrelated wording here"})
        self.assertLess(conf, 0.5)

    def test_an_unfitted_student_answers_nothing(self):
        self.assertEqual(NearestNeighbourStudent().predict({"text": "x"}), (None, 0.0))


class TheLoraStudentRefusesRatherThanPretends(unittest.TestCase):
    def test_fit_raises_instead_of_falling_back(self):
        with self.assertRaises(NotImplementedError):
            LoraStudent("some-base").fit(traced())

    def test_an_unfitted_one_refuses_to_answer(self):
        with self.assertRaises(RuntimeError):
            LoraStudent("some-base").predict({"text": "x"})


class TheRouterFallsBackAndSaysWhy(unittest.TestCase):
    def setUp(self):
        s = NearestNeighbourStudent(); s.fit(traced())
        self.r = Router(CAP, s, threshold=0.6)

    def test_a_confident_answer_comes_from_the_student(self):
        d = self.r.ask({"text": "login page broken"}, lambda i: {"label": "teacher"})
        self.assertEqual(d.answered_by, "student")

    def test_an_unsure_one_goes_to_the_teacher(self):
        d = self.r.ask({"text": "nothing like the training data at all"},
                       lambda i: {"label": "teacher"})
        self.assertEqual(d.answered_by, "teacher"); self.assertIn("below", d.reason)

    def test_a_confident_but_malformed_answer_still_falls_back(self):
        class Liar:
            def fit(self, t): pass
            def predict(self, i): return {"wrong": "shape"}, 0.99
        r = Router(CAP, Liar(), threshold=0.5)
        d = r.ask({"text": "x"}, lambda i: {"label": "teacher"})
        self.assertEqual(d.answered_by, "teacher"); self.assertIn("invalid", d.reason)

    def test_with_no_student_everything_goes_to_the_teacher(self):
        d = Router(CAP).ask({"text": "x"}, lambda i: {"label": "teacher"})
        self.assertEqual(d.answered_by, "teacher"); self.assertEqual(d.reason, "no student")

    def test_the_ledger_counts_every_decision(self):
        for q in ("login page broken", "unrelated text entirely"):
            self.r.ask({"text": q}, lambda i: {"label": "teacher"})
        self.assertEqual(self.r.stats()["asked"], 2)


class TheEvalReportsConfidentWrongSeparately(unittest.TestCase):
    def test_it_splits_and_scores(self):
        t = traced(); train, held = split(t, holdout=0.34)
        self.assertTrue(train and held)
        s = NearestNeighbourStudent(); s.fit(train)
        r = evaluate(s, held, threshold=0.5)
        self.assertEqual(r["held_out"], len(held))
        self.assertIn("confident_wrong_rate", r)

    def test_the_table_renders(self):
        t = traced(); train, held = split(t, holdout=0.34)
        s = NearestNeighbourStudent(); s.fit(train)
        out = table({"nearest-neighbour": evaluate(s, held)})
        self.assertIn("nearest-neighbour", out); self.assertIn("conf-wrong", out)


if __name__ == "__main__":
    unittest.main(verbosity=2)
