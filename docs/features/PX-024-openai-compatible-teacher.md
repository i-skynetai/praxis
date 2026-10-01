# PX-024 — OpenAI-compatible local adapter: student, System-1 and teacher

**Status:** Done (0.3.0) · **Owner:** @arupmmi07 2026-10-01 · **Issue:** —

> **Scope widened on 2026-09-30** after re-reading the original design: one adapter over
> the OpenAI-compatible wire protocol plays three roles. As a **generative student**
> (`GenerativeModel`: output against the capability's schema plus a self-reported
> confidence), as a **System-1 for decision capabilities** (`DecisionModel`: a strict JSON
> schema asking for a probability per option, calibrated by Praxis), and as a **teacher**
> (the role this note was first written for). The wire contract below is the same in all
> three; the prompt renderer and the response parser are shared. v1.0 ships it with no
> log-probabilities; the sampling-based alternative is roadmap PX-131.

The first real System-2, and the first any-model student. Labels as in PX-020: **Verified** (where), **To verify**,
**Question**. Sources re-read 2026-09-30.

## What is missing today

The only `Teacher` is the fake. Nothing in Praxis has asked a real LLM a typed question
through structured output, so the label path (System-2 answers become the dataset) has
only ever been exercised by a keyword rule.

## What the wire contract is (Verified, 2026-09-30)

| Fact | Value | Where |
|---|---|---|
| Endpoint | `POST {base_url}/chat/completions`; local Ollama base URL `http://localhost:11434/v1/` | Ollama OpenAI-compatibility page |
| Auth | `Authorization: Bearer <key>`; Ollama: "required but ignored", any value | same page |
| Structured output, JSON-schema form | `response_format: {"type": "json_schema", "json_schema": {"name", "schema", "strict": true}}` | vLLM structured-outputs page (its documented `response_format` form); confirmed live on Ollama below |
| Ollama supports it | **Yes.** A request with a strict schema of `{"department": string enum, "urgency": integer enum [0..3], "churn_risk": boolean}` to `granite4.1:8b` returned `{"department": "billing", "urgency": 2, "churn_risk": true}` in 7.1 s cold, `usage.prompt_tokens 204, completion_tokens 27` | `curl` against `http://localhost:11434/v1/chat/completions` this session |
| Ollama does not support | `tool_choice`, `logit_bias`, `user`, `n`, `logprobs` | Ollama OpenAI-compatibility page |
| Result location | `choices[0].message.content` as a JSON string; `finish_reason: "stop"` | the live response above |
| OpenAI Chat Completions `response_format` | types `text`, `json_schema` (recommended), `json_object` (older); `json_schema` fields `name` (a-z, A-Z, 0-9, `_`, `-`, max 64), `description`, `schema`, `strict`; `logprobs` / `top_logprobs` (0–20) exist; the message has a `refusal` field | OpenAI API reference, Chat Completions create |
| Strict-mode schema rules (OpenAI) | all fields `required`; `additionalProperties: false`; types string/number/boolean/array/object/null; `enum` supported | OpenAI structured-outputs guide |
| Local models available for tests | `granite4.1:8b`, `granite4.1:3b`, `llama3.2:latest`, `gemma4:12b-mlx` | `curl localhost:11434/api/tags` this session |

**To verify during the build:** whether `granite4.1:3b` is reliable enough to be the default local test model (faster
than 8b); how vLLM and LiteLLM proxies report `usage`.

## What done looks like

- The adapter satisfies `Teacher`, is standard library only (`urllib.request`, `json`),
  and needs no extra to install.
- One request per `answer()` call: a system message with the role, a user message that
  renders the state and every question (type, instructions, options or levels), and a
  strict JSON schema with one property per question: `choice` → string enum of the keys;
  `score` → integer enum `0..n-1`; `boolean` → boolean; `rank` → array of strings with an
  enum of the keys.
- The reply is parsed from `choices[0].message.content`, checked against the declared
  set (the router checks again), and returned as `TeacherAnswer(answer)`; a `refusal`
  field, a non-JSON body, or a missing question raises, which the router records and
  re-raises as `TeacherError`.
- `usage` tokens become `cost_usd` when the adapter is given a price per million tokens;
  otherwise 0.
- HTTP 429 and 5xx retry twice with backoff; a timeout (default 60 s) raises.
- Tests without network: a stdlib `http.server` on a thread returns canned completions,
  including a refusal, a malformed body and a 500. Live test against the local Ollama
  runs only when `PRAXIS_LIVE=1` and the server answers `GET /api/tags`.
- The conformance suite (PX-027) runs the same triage requests through it.
- `python -m praxis_core demo --teacher openai-compatible --base-url http://localhost:11434/v1
  --model granite4.1:8b --tickets 10` runs the four stages with a real teacher. (At about
  seven seconds a call this is minutes, not one second; the one-second promise is for
  the fake teacher and stays tested.)

## Design

`praxis_core/providers/openai_compat.py`, one class:

```
OpenAICompatibleTeacher(base_url, model, api_key=None, *, timeout_s=60.0, temperature=0.0,
                        max_tokens=512, price_per_million=(0.0, 0.0), system_prompt=None,
                        extra_body=None)
  info   -> ModelInfo("openai-compatible", model, version="", level="")
  answer(state, questions) -> {name: TeacherAnswer(answer, distribution=None, cost_usd)}
```

- `distribution` is `None` in this version: Ollama exposes no log-probabilities. The
  router records a one-hot for the label; a later change can read `logprobs` where a
  server offers them.
- `extra_body` lets a host pass provider-specific fields (vLLM's `guided_*`, a proxy's
  routing keys) without the core knowing them.
- The prompt is one function, `render(state, questions) -> str`, so the Anthropic teacher
  (PX-025) reuses it and the two teachers see the same words.
- Provider names appear only in this module and in `praxis doctor`'s registry.

**Question 3 — default local model for the live tests and the demo:** `granite4.1:8b`
(verified above) or the smaller `granite4.1:3b` once verified.

## What it does not do

No streaming, no tool calls, no images, no batching. No log-probabilities. No prompt
caching. It is a teacher, not a chat client.

## How it is measured

On the demo traffic: agreement between this teacher and the rule teacher per question
(the rule teacher is the ground truth the generator was written against), median
latency, tokens per call. Recorded here when measured.
