# Praxis

[![tests](https://github.com/arupmmi07/praxis/actions/workflows/tests.yml/badge.svg)](https://github.com/arupmmi07/praxis/actions/workflows/tests.yml)
[![python](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/downloads/)
[![licence](https://img.shields.io/badge/licence-Apache%202.0-blue)](LICENSE)

**A provider-neutral System-1 / System-2 decision and training framework.**

A capability declares typed questions about a state. A fast decision model (System-1)
answers each one with a probability distribution in milliseconds. Praxis calibrates that
distribution, computes one confidence that means the same thing for every provider, and
either **serves** the answer or **abstains** to your LLM (System-2). Every call leaves a
trace. The teacher's answers become the labels that train the next System-1, and the
teacher never leaves the loop.

```
  DecisionRequest ──► System-1 ──► calibrate ──► valid and confident?
  state + questions   (any provider)               │ yes  serve, answered_by = system1
                                                   │ no   abstain → System-2 (your LLM) → serve, and keep the answer as a label
                                                   ▼
                                       trace: both answers, both distributions, confidence, reason
```

## Try it, with nothing installed

```bash
python -m praxis demo
```

```
praxis demo: support.triage, 3 questions, fake teacher, nearest-neighbour student, threshold 0.5

stage          calls  questions  system1  abstain   agree     ms
shadow-cold       60        180      0%       0%    0.29    8.2
shadow-warm       60        180      0%       0%    0.73   19.0
canary-50%        60        180     27%      73%    0.74   20.5
serve             60        180     46%      54%       -   19.6

calibrator: boolean/2 T=0.40  choice/4 T=0.79  score/4 T=0.18
labels: 180 System-2 answers from 60 traces -> 180 examples -> student fitted
served by System-1 in the serve stage: 83; the teacher would have disagreed on 3 (confident-wrong)
240 traces recorded; the trace path raised into the caller 0 times
loop closed in 93 ms: capture -> label -> fit -> calibrate -> canary -> serve. The teacher stays.
```

`support.triage` asks three questions of a support ticket: `department` (a choice of
four), `urgency` (a score on four levels) and `churn_risk` (a boolean). A synthetic
ticket generator is the traffic, a keyword rule stands in for the System-2 teacher, and
the nearest-neighbour baseline is the System-1 student. Standard library, no keys.

## The contract

The request shape is the one the System-1 decision models have converged on: a state
plus a map of named, typed questions. Praxis adds what they lack: one confidence scale,
a flag saying whether a fitted calibrator produced it, and abstain as a recorded outcome.

| Type | Meaning | Declares | Answer |
|---|---|---|---|
| `choice` | pick one option | `options: {key: description}` | the key |
| `score` | a level on an ordered rubric | `levels: [low, ..., high]` | the level index, plus an expected value |
| `boolean` | is this statement true | just the instructions | `True` / `False` (`noul`, the vendors' name, is accepted as an alias) |
| `rank` | order the options | `options` | the keys, best first, derived from the choice distribution |

```python
from praxis import Capability, Question, DecisionRouter, RoutingPolicy

triage = Capability("support.triage", questions={
    "department": Question.choice("Which team should handle this ticket?",
                                  {"billing": "...", "technical": "...", "account": "...", "sales": "..."}),
    "urgency":    Question.score("How urgent is this ticket?", ["low", "medium", "high", "critical"]),
    "churn_risk": Question.boolean("The customer is at risk of cancelling."),
})
```

Every `DecisionResult` carries `answer`, `distribution`, `confidence` (Praxis's scale),
`native_confidence` (what the provider said, kept for audit), `calibrated`, `abstain`,
`answered_by` (`system1` | `system2`), who answered (`provider`, `model`, `version`,
`level`), `latency_ms`, `cost_usd` and the `trace_id`.

## Use it

```python
from praxis.core.baseline import NearestNeighbourDecisionModel
from praxis.core.calibrate import TemperatureCalibrator
from praxis.core.dataset import examples_from_traces
from praxis.core.trace import JsonlTraceSink

student, calibrator, sink = NearestNeighbourDecisionModel(), TemperatureCalibrator(), JsonlTraceSink("traces.jsonl")
router = DecisionRouter(triage, teacher=my_teacher,            # any object with the Teacher port
                        system1=student, calibrator=calibrator, sink=sink,
                        policy=RoutingPolicy(threshold=0.6, stage="shadow"))

results = router.decide_state({"subject": "invoice charged twice", "body": "..."})
results["urgency"].answer, results["urgency"].confidence, results["urgency"].answered_by

# Trust the loop before the model: shadow, then labels, then a fitted student, then calibrate, then serve.
examples, report = examples_from_traces(sink.read("support.triage"), triage)   # nothing is skipped silently
student.fit(examples)
calibrator.fit(list(sink.read("support.triage")))
router.set_stage("canary", canary_share=0.2)
router.set_stage("serve")
```

## What Praxis guarantees, and the test that proves each

| Guarantee | Proof |
|---|---|
| A System-1 error, timeout or malformed answer never fails the call. It is an abstention with a reason, and the teacher serves. | `tests/test_router.py::FaultInjectionNeverFailsTheCall` — including 100 hostile calls, 100 % served by System-2 |
| The trace path never raises into the caller. A broken sink is counted, not raised. | `tests/test_router.py::TheTracePathNeverRaises` |
| Abstain is a recorded outcome, not an error. | `tests/test_router.py::ServeAndAbstain` |
| Shadow records both answers side by side. | `tests/test_router.py::ShadowRecordsBothAnswers` |
| One confidence scale for every provider: `1 - H(p)/log(n)` on the calibrated distribution. | `tests/test_calibrator.py`, `tests/test_contracts.py` |
| The teacher is permanent. A confident System-1 needs no teacher; a failing teacher is recorded, then raised. | `tests/test_router.py::TheTeacherIsTheOnlyThingThatCanFail` |
| An unfitted student is never served. | `tests/test_baseline.py` |
| The core is standard library only, and no provider name appears outside `praxis/providers/`. | `tests/test_contracts.py::TheCoreIsStandardLibraryOnly` |
| The whole loop closes in under a second with nothing installed. | `tests/test_demo.py` |

## The parts

| | |
|---|---|
| **contracts** | `Question`, `Capability` (kind = `decision` \| `generative`), `DecisionRequest`, `DecisionResult`, `DecisionExample`, and the trace envelope v2: a stable Praxis envelope, an opaque host partition key, an opaque payload. |
| **ports** | Seven `Protocol`s: `DecisionModel`, `Teacher`, `Calibrator`, `Trainer`, `TraceSink`, `SchemaValidator`, `Registry`, plus the sibling `GenerativeModel`. One fake per port ships in `praxis.providers.fake`. |
| **router** | Eight steps per call: policy, timed and bounded System-1 call, calibrate, validate, serve or abstain per question, teacher for the rest (everything, in shadow), record. |
| **calibrator** | One temperature per (question type, option count), fitted on traces that carry both answers. No gradients, no dependency. |
| **sinks** | JSONL and SQLite. Both round-trip the envelope and read back by capability. |
| **baseline** | The nearest-neighbour student behind the `DecisionModel` port: a distribution from similarity-weighted votes, the best similarity kept as `native_confidence`. Exists so the loop is demonstrably closed and a real model has a number to beat. |
| **seam, gate, student, evaluate** | The original modules, kept for the generative path: the four-check gate, the confident-wrong metric, and a `LoraStudent` whose `fit` raises until a backend is wired in. |

## Ports and adapters

| Port | Today | Planned (see [ROADMAP.md](ROADMAP.md)) |
|---|---|---|
| `DecisionModel` | `fake`, `nearest-neighbour` | a local Apple-Silicon decision model first, then a PyTorch one, a read-out layer over any open LLM, and an HTTP adapter for the hosted API and its self-hosted twin |
| `Teacher` | `fake` | an OpenAI-compatible adapter (covers local servers and proxies), an Anthropic adapter |
| `Calibrator` | `temperature` | Platt, isotonic |
| `Trainer` | `fake` | temperature refit, a closed-form head, the published fine-tuning path |
| `TraceSink` | `jsonl`, `sqlite`, `fake` | Postgres, object store |
| `SchemaValidator` | `dict-of-types` | Pydantic, JSON Schema |
| `Registry` | `fake` | a local JSON manifest |

The core promises the contract, not an adapter. `pip install praxis` is standard library
only; each adapter is a pip extra.

## The training ladder

Climb per capability and stop at the first rung whose scorecard clears the gate.
**A** use a pretrained decision model as shipped and fit a temperature on gated traces
(minutes, CPU). **B** fit a head or a threshold on labelled traces, no gradients
(seconds). **C** fine-tune the decision model on the decision dataset, then recalibrate
(hours, a small GPU). **D** LoRA a small causal LM, for generative capabilities only.
Rung A alone clears the gate for a large share of routing-type capabilities.

## Documentation

| | |
|---|---|
| [Architecture](docs/architecture.md) | The contract, the eight router steps, the envelope, and where each decision is made |
| [Roadmap](ROADMAP.md) | Every planned feature with an ID, a status and an owner |
| [Distillation](docs/distillation.md) | The generative path: wiring a LoRA student, and what to measure first |
| [Contributing](CONTRIBUTING.md) | Running the checks, and what a change needs |

## Status

Python 3.11+, standard library only at runtime. **114 tests**, run by CI on 3.11 to
3.14; `mypy --strict` on the core, the providers and the CLI. Phases 0 (contracts) and 1
(router, calibrator, capture) are done; Phase 2 (provider adapters) is next.

## Licence

Apache 2.0.
