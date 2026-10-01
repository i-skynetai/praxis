"""PX-024: one adapter over the OpenAI-compatible wire protocol in three roles, tested
against a standard-library fake server. The live test against a local server runs only
when PRAXIS_LIVE=1 and the server answers."""

from __future__ import annotations

import json
import os
import threading
import unittest
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from praxis_core.contracts import Capability, Question
from praxis_core.demo import support_extract
from praxis_core.ports import DecisionModel, GenerativeModel, Teacher
from praxis_core.providers._extras import require
from praxis_core.providers.fake import FakeTraceSink
from praxis_core.providers.openai_compat import (
    CONFIDENCE_FIELD,
    OpenAICompatible,
    ProviderError,
    answers_schema,
    distributions_schema,
    output_schema_json,
)
from praxis_core.router import DecisionRouter, GenerativeRouter, RoutingPolicy, TeacherError
from tests.helpers import triage_capability

CAP = triage_capability()
EXTRACT = support_extract()
TICKET = {
    "subject": "invoice charged twice",
    "body": "why was I charged twice on the invoice for my Nimbus router, "
    "order #AB1234. we need this today. we might switch providers.",
}


def completion(content: Any, usage: dict[str, int] | None = None, refusal: str | None = None) -> dict[str, Any]:
    message: dict[str, Any] = {
        "role": "assistant",
        "content": content if isinstance(content, str) else json.dumps(content),
    }
    if refusal is not None:
        message["refusal"] = refusal
    return {
        "id": "x",
        "object": "chat.completion",
        "model": "fake",
        "choices": [{"index": 0, "message": message, "finish_reason": "stop"}],
        "usage": usage or {"prompt_tokens": 100, "completion_tokens": 20},
    }


class FakeServer:
    """Serves a queue of (status, body) replies and records every request body."""

    def __init__(self) -> None:
        self.replies: list[tuple[int, Any]] = []
        self.requests: list[dict[str, Any]] = []
        server = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802
                length = int(self.headers.get("Content-Length", "0"))
                server.requests.append(
                    {
                        "path": self.path,
                        "headers": dict(self.headers),
                        "body": json.loads(self.rfile.read(length) or b"{}"),
                    }
                )
                status, body = server.replies.pop(0) if server.replies else (200, completion({}))
                payload = body if isinstance(body, (bytes, str)) else json.dumps(body)
                raw = payload.encode() if isinstance(payload, str) else payload
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def log_message(self, *args: Any) -> None:
                pass

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.httpd.server_address[1]}/v1"

    def close(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()


class TheAdapterSpeaksTheWireProtocol(unittest.TestCase):
    def setUp(self) -> None:
        self.server = FakeServer()
        self.adapter = OpenAICompatible(
            self.server.base_url, "test-model", "secret", backoff_s=0.0, price_per_million=(1.0, 10.0)
        )

    def tearDown(self) -> None:
        self.server.close()

    def test_it_satisfies_all_three_ports(self):
        self.assertIsInstance(self.adapter, GenerativeModel)
        self.assertIsInstance(self.adapter, DecisionModel)
        self.assertIsInstance(self.adapter, Teacher)
        self.assertEqual(self.adapter.info.provider, "openai-compatible")

    def test_teacher_role_sends_a_strict_schema_and_parses_typed_answers(self):
        self.server.replies.append((200, completion({"department": "billing", "urgency": 2, "churn_risk": True})))
        answers = self.adapter.answer(TICKET, CAP.questions)
        self.assertEqual(answers["department"].answer, "billing")
        self.assertEqual(answers["urgency"].answer, 2)
        self.assertIs(answers["churn_risk"].answer, True)
        self.assertAlmostEqual(answers["department"].cost_usd, (100 * 1.0 + 20 * 10.0) / 1e6)
        self.assertEqual(answers["urgency"].cost_usd, 0.0, "cost is attributed once per call")
        req = self.server.requests[0]
        self.assertEqual(req["path"], "/v1/chat/completions")
        self.assertEqual(req["headers"]["Authorization"], "Bearer secret")
        body = req["body"]
        self.assertEqual(body["model"], "test-model")
        self.assertEqual(body["response_format"]["type"], "json_schema")
        schema = body["response_format"]["json_schema"]["schema"]
        self.assertEqual(schema, answers_schema(CAP.questions))
        self.assertEqual(schema["properties"]["department"]["enum"], ["billing", "technical", "account", "sales"])
        self.assertEqual(schema["properties"]["urgency"], {"type": "integer", "enum": [0, 1, 2, 3]})
        self.assertEqual(schema["properties"]["churn_risk"], {"type": "boolean"})
        self.assertFalse(schema["additionalProperties"])
        self.assertIn("invoice charged twice", body["messages"][1]["content"])
        self.assertIn("Which team should handle this ticket?", body["messages"][1]["content"])

    def test_teacher_role_coerces_and_rejects(self):
        self.server.replies.append((200, completion({"department": "billing", "urgency": "2", "churn_risk": "false"})))
        answers = self.adapter.answer(TICKET, CAP.questions)
        self.assertEqual(answers["urgency"].answer, 2)
        self.assertIs(answers["churn_risk"].answer, False)
        rank = Capability("support.rank", questions={"order": Question.rank("Order.", {"a": "A", "b": "B"})})
        self.server.replies.append((200, completion({"order": ["b", "a"]})))
        self.assertEqual(self.adapter.answer("x", rank.questions)["order"].answer, ["b", "a"])
        self.server.replies.append((200, completion({"department": "billing", "urgency": "high", "churn_risk": True})))
        with self.assertRaises(ProviderError):
            self.adapter.answer(TICKET, CAP.questions)
        self.server.replies.append((200, completion({"department": "billing"})))
        with self.assertRaises(ProviderError):
            self.adapter.answer(TICKET, CAP.questions)

    def test_system1_role_asks_for_distributions_and_normalises(self):
        self.server.replies.append(
            (
                200,
                completion(
                    {
                        "department": {"billing": 8, "technical": 1, "account": 0.5, "sales": 0.5},
                        "urgency": {"0": 0.1, "1": 0.2, "2": 0.6, "3": 0.1},
                        "churn_risk": {"true": 0.7, "false": 0.3},
                    }
                ),
            )
        )
        raw = self.adapter.decide(TICKET, CAP.questions)
        self.assertAlmostEqual(sum(raw["department"].distribution.values()), 1.0)
        self.assertAlmostEqual(raw["department"].distribution["billing"], 0.8)
        self.assertAlmostEqual(raw["department"].native_confidence or 0.0, 0.8)
        self.assertEqual(raw["churn_risk"].distribution, {"true": 0.7, "false": 0.3})
        schema = self.server.requests[0]["body"]["response_format"]["json_schema"]["schema"]
        self.assertEqual(schema, distributions_schema(CAP.questions))
        self.assertIn("sum to 1", self.server.requests[0]["body"]["messages"][1]["content"])
        self.server.replies.append(
            (
                200,
                completion(
                    {
                        "department": {"billing": 0, "technical": 0, "account": 0, "sales": 0},
                        "urgency": {},
                        "churn_risk": {},
                    }
                ),
            )
        )
        with self.assertRaises(ProviderError):
            self.adapter.decide(TICKET, CAP.questions)

    def test_generative_role_strips_the_confidence_field(self):
        self.server.replies.append(
            (
                200,
                completion(
                    {"product": "Nimbus router", "issue": "double_charge", "order_id": "AB1234", CONFIDENCE_FIELD: 0.83}
                ),
            )
        )
        answer = self.adapter.generate(TICKET, EXTRACT.instructions, EXTRACT.output_schema)
        self.assertEqual(answer.output, {"product": "Nimbus router", "issue": "double_charge", "order_id": "AB1234"})
        self.assertAlmostEqual(answer.confidence, 0.83)
        schema = self.server.requests[0]["body"]["response_format"]["json_schema"]["schema"]
        self.assertEqual(schema, output_schema_json(EXTRACT.output_schema))
        self.assertIn(CONFIDENCE_FIELD, schema["required"])
        self.server.replies.append((200, completion({"product": "x", "issue": "y", "order_id": ""})))
        self.assertEqual(
            self.adapter.generate(TICKET, "", EXTRACT.output_schema).confidence, 0.0, "missing confidence is 0"
        )

    def test_refusals_bad_bodies_and_http_errors(self):
        self.server.replies.append((200, completion("", refusal="I cannot help with that")))
        with self.assertRaises(ProviderError) as cm:
            self.adapter.answer(TICKET, CAP.questions)
        self.assertIn("refused", str(cm.exception))
        self.server.replies.append((200, completion("not json at all")))
        with self.assertRaises(ProviderError):
            self.adapter.answer(TICKET, CAP.questions)
        self.server.replies.append((200, b"<html>"))
        with self.assertRaises(ProviderError):
            self.adapter.answer(TICKET, CAP.questions)
        self.server.replies.append((400, {"error": "bad request"}))
        with self.assertRaises(ProviderError) as cm2:
            self.adapter.answer(TICKET, CAP.questions)
        self.assertEqual(cm2.exception.status, 400)
        self.assertEqual(len(self.server.requests), 4, "a 400 is not retried")

    def test_429_and_5xx_are_retried_then_raised(self):
        self.server.replies.extend(
            [
                (503, {"error": "busy"}),
                (429, {"error": "slow down"}),
                (200, completion({"department": "billing", "urgency": 1, "churn_risk": False})),
            ]
        )
        answers = self.adapter.answer(TICKET, CAP.questions)
        self.assertEqual(answers["department"].answer, "billing")
        self.assertEqual(len(self.server.requests), 3)
        self.server.replies.extend([(500, {}), (500, {}), (500, {})])
        with self.assertRaises(ProviderError) as cm:
            self.adapter.answer(TICKET, CAP.questions)
        self.assertEqual(cm.exception.status, 500)
        self.assertEqual(len(self.server.requests), 6, "two retries, then give up")

    def test_an_unreachable_server_is_a_provider_error(self):
        dead = OpenAICompatible("http://127.0.0.1:9/v1", "m", retries=0, timeout_s=1.0)
        with self.assertRaises(ProviderError):
            dead.answer(TICKET, CAP.questions)

    def test_through_the_routers_a_failing_student_abstains_and_a_failing_teacher_is_a_teacher_error(self):
        self.server.replies.append((500, {}))
        student = OpenAICompatible(self.server.base_url, "m", retries=0)
        from praxis_core.providers.fake import FakeTeacher
        from tests.helpers import oracle

        router = DecisionRouter(CAP, FakeTeacher(oracle), student, None, FakeTraceSink(), RoutingPolicy(0.5))
        results = router.decide_state(TICKET)
        self.assertTrue(all(r.answered_by == "system2" and r.reason.startswith("error:") for r in results.values()))
        self.server.replies.append((500, {}))
        router2 = DecisionRouter(CAP, student, None, None, FakeTraceSink(), RoutingPolicy(0.5))
        with self.assertRaises(TeacherError):
            router2.decide_state(TICKET)
        self.server.replies.append(
            (
                200,
                completion(
                    {"product": "Nimbus router", "issue": "double_charge", "order_id": "AB1234", CONFIDENCE_FIELD: 0.9}
                ),
            )
        )
        gen = GenerativeRouter(EXTRACT, student, None, None, FakeTraceSink(), RoutingPolicy(0.5))
        self.assertEqual(gen.generate_state(TICKET).output["order_id"], "AB1234")

    def test_extra_body_and_system_prompt_pass_through(self):
        adapter = OpenAICompatible(self.server.base_url, "m", system_prompt="Be terse.", extra_body={"seed": 7})
        self.server.replies.append((200, completion({"department": "sales", "urgency": 0, "churn_risk": False})))
        adapter.answer(TICKET, CAP.questions)
        body = self.server.requests[0]["body"]
        self.assertEqual(body["seed"], 7)
        self.assertEqual(body["messages"][0]["content"], "Be terse.")


class TheExtrasRule(unittest.TestCase):
    def test_a_missing_dependency_names_its_extra(self):
        with self.assertRaises(ImportError) as cm:
            require("no_such_module_praxis", "laya-mlx", "the Apple-Silicon decision model")
        self.assertIn('pip install "praxis-core[laya-mlx]"', str(cm.exception))
        self.assertIs(require("json", "none"), json)

    def test_importing_the_providers_package_pulls_no_vendor_module(self):
        import sys

        import praxis_core.providers  # noqa: F401
        import praxis_core.providers.openai_compat  # noqa: F401

        for vendor in ("mlx", "laya_mlx", "openai", "anthropic", "torch", "transformers"):
            self.assertNotIn(vendor, sys.modules)


def _live_server() -> str | None:
    if os.environ.get("PRAXIS_LIVE") != "1":
        return None
    base = os.environ.get("PRAXIS_LIVE_BASE_URL", "http://localhost:11434/v1")
    try:
        with urllib.request.urlopen(base.rsplit("/v1", 1)[0] + "/api/tags", timeout=3) as r:
            r.read()
    except Exception:  # noqa: BLE001
        return None
    return base


@unittest.skipUnless(_live_server(), "set PRAXIS_LIVE=1 with a local OpenAI-compatible server to run")
class LiveAgainstALocalServer(unittest.TestCase):
    def test_all_three_roles_on_the_sample_ticket(self):
        base = _live_server()
        assert base is not None
        adapter = OpenAICompatible(base, os.environ.get("PRAXIS_LIVE_MODEL", "granite4.1:8b"), "ollama", timeout_s=180)
        answers = adapter.answer(TICKET, CAP.questions)
        for name, q in CAP.questions.items():
            self.assertTrue(q.is_valid_answer(answers[name].answer), (name, answers[name].answer))
        raw = adapter.decide(TICKET, CAP.questions)
        for name in CAP.questions:
            self.assertAlmostEqual(sum(raw[name].distribution.values()), 1.0, places=6)
        out = adapter.generate(TICKET, EXTRACT.instructions, EXTRACT.output_schema)
        self.assertEqual(set(out.output), set(EXTRACT.output_schema))
        self.assertTrue(0.0 <= out.confidence <= 1.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
