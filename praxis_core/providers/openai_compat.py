"""One adapter over the OpenAI-compatible chat-completions wire protocol, in three roles.

Local servers, proxies and the hosted API share one request shape: ``POST
{base_url}/chat/completions`` with ``messages`` and a strict JSON-schema
``response_format``. Verified on a local Ollama on 2026-09-30 (a strict schema with
string-enum, integer-enum and boolean fields was honoured); the Chat Completions
``response_format`` form is documented by OpenAI and by vLLM. Standard library only:
``urllib`` for HTTP, ``json`` for the body, no SDK.

The three roles, each a port from ``praxis_core.ports``:

* ``GenerativeModel`` — ``generate(state, instructions, output_schema)``: the output
  against the capability's schema plus a self-reported confidence (asked for as one
  more field, ``_confidence``, stripped before the output is returned).
* ``DecisionModel`` — ``decide(state, questions)``: a probability per option for every
  question, normalised; ``native_confidence`` is the top probability. No
  log-probabilities are read in this version (local servers rarely expose them);
  self-report is calibrated by Praxis like any other provider's number.
* ``Teacher`` — ``answer(state, questions)``: one typed answer per question.

Failures raise ``ProviderError``; the routers turn a student's failure into an
abstention and a teacher's into ``TeacherError`` after the trace is recorded. Nothing
here catches its own mistakes, so the failure rate stays visible.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any, Mapping

from praxis_core.contracts import (
    Answer,
    GenerativeAnswer,
    ModelInfo,
    Question,
    RawAnswer,
    State,
    TeacherAnswer,
    is_finite,
)

PROVIDER = "openai-compatible"
CONFIDENCE_FIELD = "_confidence"
_JSON_TYPES: dict[str, dict[str, Any]] = {
    "str": {"type": "string"}, "int": {"type": "integer"}, "float": {"type": "number"},
    "bool": {"type": "boolean"}, "list": {"type": "array", "items": {"type": "string"}},
    "dict": {"type": "object", "additionalProperties": True},
}
DEFAULT_SYSTEM_PROMPT = ("You answer typed questions about a state. Read the state, then answer every question. "
                         "Reply with JSON only, matching the schema exactly.")


class ProviderError(RuntimeError):
    """The server failed, refused, or answered something that is not an answer."""

    def __init__(self, message: str, status: int | None = None, retryable: bool = False) -> None:
        super().__init__(message)
        self.status = status
        self.retryable = retryable


# ------------------------------------------------------------------ rendering

def render_state(state: State) -> str:
    return state if isinstance(state, str) else json.dumps(state, sort_keys=True, ensure_ascii=False)


def render_questions(questions: Mapping[str, Question], *, probabilities: bool) -> str:
    """The questions as text. With ``probabilities`` the model is asked for a distribution
    per question instead of one answer."""
    lines = ["Questions:"]
    for name, q in questions.items():
        if q.type in ("choice", "rank"):
            options = "; ".join(f"{k} = {v}" for k, v in q.options.items())
            kind = "rank every option, best first" if q.type == "rank" else "choose one option"
            lines.append(f"- {name} ({kind}: {options}): {q.instructions}")
        elif q.type == "score":
            levels = "; ".join(f"{i} = {level}" for i, level in enumerate(q.levels))
            lines.append(f"- {name} (score, one level 0..{len(q.levels) - 1}: {levels}): {q.instructions}")
        else:
            lines.append(f"- {name} (true or false): {q.instructions}")
    if probabilities:
        lines.append("For every question give a probability for each option (for a true-or-false question, for "
                     "\"true\" and \"false\"). The probabilities of one question must sum to 1.")
    return "\n".join(lines)


def render_generative(instructions: str, output_schema: Mapping[str, str]) -> str:
    fields = ", ".join(f"{k} ({t})" for k, t in output_schema.items())
    return (f"Task: {instructions}\nReturn an object with the fields: {fields}, plus {CONFIDENCE_FIELD}: "
            f"your confidence between 0 and 1 that the whole object is correct.")


# -------------------------------------------------------------------- schemas

def answers_schema(questions: Mapping[str, Question]) -> dict[str, Any]:
    """One property per question: the typed answer."""
    props: dict[str, Any] = {}
    for name, q in questions.items():
        if q.type == "choice":
            props[name] = {"type": "string", "enum": list(q.options)}
        elif q.type == "rank":
            props[name] = {"type": "array", "items": {"type": "string", "enum": list(q.options)}}
        elif q.type == "score":
            props[name] = {"type": "integer", "enum": list(range(len(q.levels)))}
        else:
            props[name] = {"type": "boolean"}
    return {"type": "object", "properties": props, "required": list(questions), "additionalProperties": False}


def distributions_schema(questions: Mapping[str, Question]) -> dict[str, Any]:
    """One property per question: an object with a probability per option."""
    props: dict[str, Any] = {}
    for name, q in questions.items():
        keys = list(q.keys())
        props[name] = {"type": "object", "properties": {k: {"type": "number"} for k in keys},
                       "required": keys, "additionalProperties": False}
    return {"type": "object", "properties": props, "required": list(questions), "additionalProperties": False}


def output_schema_json(output_schema: Mapping[str, str], with_confidence: bool = True) -> dict[str, Any]:
    props: dict[str, Any] = {k: dict(_JSON_TYPES.get(t, {"type": "string"})) for k, t in output_schema.items()}
    required = list(output_schema)
    if with_confidence:
        props[CONFIDENCE_FIELD] = {"type": "number"}
        required.append(CONFIDENCE_FIELD)
    return {"type": "object", "properties": props, "required": required, "additionalProperties": False}


# -------------------------------------------------------------------- adapter

class OpenAICompatible:
    """The adapter. ``base_url`` ends at ``/v1`` (for a local Ollama: ``http://localhost:11434/v1``)."""

    def __init__(self, base_url: str, model: str, api_key: str | None = None, *, timeout_s: float = 60.0,
                 temperature: float = 0.0, max_tokens: int = 512, price_per_million: tuple[float, float] = (0.0, 0.0),
                 system_prompt: str | None = None, extra_body: Mapping[str, Any] | None = None,
                 retries: int = 2, backoff_s: float = 0.5, info: ModelInfo | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout_s = timeout_s
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.price_per_million = price_per_million
        self.system_prompt = system_prompt or DEFAULT_SYSTEM_PROMPT
        self.extra_body = dict(extra_body or {})
        self.retries = retries
        self.backoff_s = backoff_s
        self._info = info or ModelInfo(PROVIDER, model, "", "self-report")
        self.calls = 0
        self.last_usage: dict[str, int] = {}

    @property
    def info(self) -> ModelInfo:
        return self._info

    # roles -------------------------------------------------------------------
    def generate(self, state: State, instructions: str, output_schema: Mapping[str, str]) -> GenerativeAnswer:
        user = f"State:\n{render_state(state)}\n\n{render_generative(instructions, output_schema)}"
        data, cost = self._complete(user, output_schema_json(output_schema), "praxis_output")
        raw_conf = data.pop(CONFIDENCE_FIELD, None)
        confidence = min(1.0, max(0.0, float(raw_conf))) if is_finite(raw_conf) else 0.0
        return GenerativeAnswer(data, confidence, cost)

    def decide(self, state: State, questions: Mapping[str, Question]) -> Mapping[str, RawAnswer]:
        user = f"State:\n{render_state(state)}\n\n{render_questions(questions, probabilities=True)}"
        data, cost = self._complete(user, distributions_schema(questions), "praxis_distributions")
        out: dict[str, RawAnswer] = {}
        for i, (name, q) in enumerate(questions.items()):
            given = data.get(name)
            if not isinstance(given, Mapping):
                raise ProviderError(f"no distribution for {name!r} in the reply")
            keys = q.keys()
            weights = {k: max(0.0, float(given.get(k, 0.0))) for k in keys if is_finite(given.get(k, 0.0))}
            total = sum(weights.values())
            if len(weights) != len(keys) or total <= 0.0:
                raise ProviderError(f"distribution for {name!r} is not usable: {given!r}")
            distribution = {k: weights[k] / total for k in keys}
            out[name] = RawAnswer(distribution, max(distribution.values()), cost if i == 0 else 0.0)
        return out

    def answer(self, state: State, questions: Mapping[str, Question]) -> Mapping[str, TeacherAnswer]:
        user = f"State:\n{render_state(state)}\n\n{render_questions(questions, probabilities=False)}"
        data, cost = self._complete(user, answers_schema(questions), "praxis_answers")
        out: dict[str, TeacherAnswer] = {}
        for i, (name, q) in enumerate(questions.items()):
            if name not in data:
                raise ProviderError(f"no answer for {name!r} in the reply")
            out[name] = TeacherAnswer(self._coerce(q, data[name]), None, cost if i == 0 else 0.0)
        return out

    # wire --------------------------------------------------------------------
    @staticmethod
    def _coerce(question: Question, value: Any) -> Answer:
        if question.type == "boolean":
            if isinstance(value, bool):
                return value
            if isinstance(value, str) and value.strip().lower() in ("true", "false"):
                return value.strip().lower() == "true"
            raise ProviderError(f"boolean answer expected, got {value!r}")
        if question.type == "score":
            if isinstance(value, bool):
                raise ProviderError(f"level index expected, got {value!r}")
            if isinstance(value, (int, float)) and float(value).is_integer():
                return int(value)
            if isinstance(value, str) and value.strip().lstrip("-").isdigit():
                return int(value.strip())
            raise ProviderError(f"level index expected, got {value!r}")
        if question.type == "rank":
            if isinstance(value, list):
                return [str(v) for v in value]
            raise ProviderError(f"a list of option keys expected, got {value!r}")
        if isinstance(value, str):
            return value
        raise ProviderError(f"an option key expected, got {value!r}")

    def _complete(self, user: str, schema: Mapping[str, Any], name: str) -> tuple[dict[str, Any], float]:
        body: dict[str, Any] = {
            "model": self.model, "temperature": self.temperature, "max_tokens": self.max_tokens,
            "messages": [{"role": "system", "content": self.system_prompt}, {"role": "user", "content": user}],
            "response_format": {"type": "json_schema", "json_schema": {"name": name, "strict": True, "schema": dict(schema)}},
        }
        body.update(self.extra_body)
        reply = self._post("/chat/completions", body)
        choices = reply.get("choices")
        if not isinstance(choices, list) or not choices:
            raise ProviderError("reply has no choices")
        message = choices[0].get("message") if isinstance(choices[0], Mapping) else None
        if not isinstance(message, Mapping):
            raise ProviderError("reply has no message")
        if message.get("refusal"):
            raise ProviderError(f"the model refused: {message['refusal']}")
        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            raise ProviderError("reply has no content")
        try:
            data = json.loads(content)
        except json.JSONDecodeError as exc:
            raise ProviderError(f"reply is not JSON: {exc}") from exc
        if not isinstance(data, dict):
            raise ProviderError(f"reply is not an object: {type(data).__name__}")
        usage_raw = reply.get("usage")
        usage: Mapping[str, Any] = usage_raw if isinstance(usage_raw, Mapping) else {}
        prompt_tokens = int(usage.get("prompt_tokens", 0) or 0)
        completion_tokens = int(usage.get("completion_tokens", 0) or 0)
        self.last_usage = {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens}
        cost = (prompt_tokens * self.price_per_million[0] + completion_tokens * self.price_per_million[1]) / 1_000_000
        return data, cost

    def _post(self, path: str, body: Mapping[str, Any]) -> dict[str, Any]:
        payload = json.dumps(body).encode("utf-8")
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        attempt = 0
        while True:
            self.calls += 1
            request = urllib.request.Request(self.base_url + path, data=payload, headers=headers, method="POST")
            try:
                with urllib.request.urlopen(request, timeout=self.timeout_s) as response:
                    raw = response.read()
                    status = int(response.status)
            except urllib.error.HTTPError as exc:
                status = int(exc.code)
                snippet = exc.read()[:300].decode("utf-8", "replace")
                error = ProviderError(f"HTTP {status} from {self.base_url}{path}: {snippet}", status,
                                      retryable=status == 429 or status >= 500)
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                error = ProviderError(f"{type(exc).__name__} talking to {self.base_url}{path}: {exc}", None, retryable=True)
            else:
                if status >= 400:
                    raise ProviderError(f"HTTP {status}", status)
                try:
                    parsed = json.loads(raw.decode("utf-8"))
                except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                    raise ProviderError(f"reply body is not JSON: {exc}") from exc
                if not isinstance(parsed, dict):
                    raise ProviderError("reply body is not an object")
                return parsed
            if not error.retryable or attempt >= self.retries:
                raise error
            time.sleep(self.backoff_s * (2 ** attempt))
            attempt += 1
