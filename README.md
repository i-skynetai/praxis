# Praxis

[![tests](https://github.com/arupmmi07/praxis/actions/workflows/tests.yml/badge.svg)](https://github.com/arupmmi07/praxis/actions/workflows/tests.yml)
[![python](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/downloads/)
[![licence](https://img.shields.io/badge/licence-Apache%202.0-blue)](LICENSE)

**Capture what your main model does. Fit a small student from it. Serve the student by
confidence, with the main model as the permanent fallback.**

Your app already makes calls to a big model for narrow jobs: which team gets this
ticket, how urgent is it, pull the order id out of it. Praxis watches those calls (one
line, never fails the request), turns the answers into a dataset, fits a small student of
any kind (a decision model, a small local LLM, a baseline), measures it against the main
model on identical inputs, tells you whether it is ready, and serves it behind confidence
routing: shadow → canary → serve, with the main model catching everything the student is
not sure about. Every call leaves a trace. Nothing here needs a cloud or a key.

```
  your app ──► its own model ──► praxis.observe(request, answer)      ← the wedge: capture first
                                        │
                                        ▼  traces → dataset → fit a student → measure → verdict
                                        │
  your app ──► praxis.decide(request) ──► student ──► calibrate ──► valid and confident?
                                                                     │ yes  serve (system1)
                                                                     │ no   abstain → main model (system2), keep the label
```

Two capability kinds, one loop: **decision** (typed questions: choice, score, yes-no)
and **generative** (an output against a schema: extraction, structured generation).

## Try it, with nothing installed

```bash
git clone <this repository> && cd praxis
python -m praxis_core demo          # or: pip install -e . && praxis demo
```

```
praxis demo: support.triage, 3 questions, fake-teacher teacher, nearest-neighbour student, threshold 0.5

stage          calls  questions  system1  abstain   agree     ms
observe           60        180      0%       0%    0.28    7.1
shadow-warm       60        180      0%       0%    0.79   20.8
verdict: ready for canary: agreement 0.79 on 180, calibrator fitted
canary-50%        60        180     31%      69%    0.72   21.8
serve             60        180     61%      39%       -   19.1

calibrator: boolean/2 T=0.24  choice/4 T=0.57  score/4 T=0.19
labels: 180 System-2 answers from 60 traces -> 180 examples -> student fitted
served by System-1 in the serve stage: 110; the teacher would have disagreed on 5 (confident-wrong)

support.extract: 3 fields, fake-extract-teacher teacher, nearest-neighbour-generative student, threshold 0.5

stage          calls  questions  system1  abstain   agree     ms
observe           60         60      0%       0%       -    2.8
shadow-warm       60         60      0%       0%    0.00   10.0
verdict: stays in shadow: shadow agreement 0.00 < 0.5; calibrator not fitted
canary-50%        60         60      0%     100%    0.02    9.0
serve             60         60      0%     100%    0.03    8.6

calibrator: platt not fitted
labels: 60 System-2 outputs -> 60 examples -> student fitted
served by System-1 in the serve stage: 0; the teacher would have disagreed on 0 (confident-wrong)
the policy requires a fitted calibrator, so nothing was served: a student that copies its nearest neighbour cannot extract, and Praxis says so instead of serving it

480 traces recorded; the trace path raised into the caller 0 times
loop closed in 123 ms: capture -> label -> fit -> calibrate -> canary -> serve, for both kinds. The teacher stays.
```

`support.triage` asks three questions of a support ticket: `department` (a choice of
four), `urgency` (a score on four levels) and `churn_risk` (a boolean). `support.extract`
pulls `product`, `issue` and `order_id` out of the same tickets. A synthetic ticket
generator is the traffic, keyword rules stand in for the main model, and the
nearest-neighbour baselines are the students. The first stage is **observe mode**: the
demo plays the app, calls "its own model" itself, and reports the answers to Praxis.

Read the second table carefully: it is the point of the project. The copy-the-nearest-
neighbour baseline cannot extract (0 % agreement in shadow), so the verdict keeps it in
shadow and the policy serves nothing. Praxis said no instead of serving 63 wrong answers,
which is what the first version of this demo did before `require_calibrated` existed.

To run the same demo with a real local model as the teacher (any server speaking the
chat-completions protocol, for example a local Ollama):

```bash
python -m praxis_core demo --provider http://localhost:11434/v1 --model granite4.1:3b --roles teacher --tickets 5
```

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
from praxis_core import Capability, Question, DecisionRouter, RoutingPolicy

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

**Step 1, capture.** Your app keeps calling its own model. Add one line after the call:

```python
from praxis_core import DecisionRouter, ModelInfo, RoutingPolicy
from praxis_core.trace import JsonlTraceSink, QueuedTraceSink

sink = QueuedTraceSink(JsonlTraceSink("traces.jsonl"))            # capture costs microseconds
router = DecisionRouter(triage, teacher=my_teacher, sink=sink, policy=RoutingPolicy(stage="shadow"))

answers = my_big_model(ticket)                                    # your call, unchanged
router.observe_state(ticket, answers, ModelInfo("my-provider", "big-model"), latency_ms=820)   # never raises
```

**Step 2, a student.** When traces exist, fit one and run it in shadow beside the app's
answers; the verdict tells you when it is ready:

```python
from praxis_core.baseline import NearestNeighbourDecisionModel
from praxis_core.calibrate import TemperatureCalibrator
from praxis_core.dataset import examples_from_traces

examples, report = examples_from_traces(sink.read("support.triage"), triage)   # every skip is reported
student = NearestNeighbourDecisionModel(); student.fit(examples)
router = DecisionRouter(triage, teacher=my_teacher, system1=student, calibrator=TemperatureCalibrator(),
                        sink=sink, policy=RoutingPolicy(threshold=0.6, stage="shadow", require_calibrated=True))
# ... more observe or decide calls in shadow, then:
router.calibrator.fit(list(sink.read("support.triage")))
```

**Step 3, serve by confidence.** Let Praxis make the call: the student answers what it is
sure about, the main model the rest, and every call is traced.

```python
router.set_stage("canary", canary_share=0.2)
results = router.decide_state({"subject": "invoice charged twice", "body": "..."})
results["urgency"].answer, results["urgency"].confidence, results["urgency"].answered_by   # 2, 0.71, "system1"
router.set_stage("serve")
```

A generative capability works the same way through `GenerativeRouter` with an
`output_schema` instead of questions; `praxis_core.demo` has both.

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
| The core is standard library only, and no provider name appears outside `praxis_core/providers/`. | `tests/test_contracts.py::TheCoreIsStandardLibraryOnly` |
| Capture never fails the request and adds no visible latency: observe mode never raises; the background sink returns in microseconds and counts drops. | `tests/test_router.py::ObserveModeNeverTouchesTheRequestPath`, `tests/test_sinks.py::TheBackgroundSinkCostsTheCallerNothing` |
| Nothing is served without a fitted calibrator when the policy says so. | `tests/test_generative.py`, `tests/test_router.py` (`require_calibrated`) |
| A captured trace rebuilds the request it recorded. | `tests/test_router.py` (replay equivalence) |
| The whole loop closes in under a second with nothing installed, for both kinds. | `tests/test_demo.py` |

## The parts

| | |
|---|---|
| **contracts** | `Question`, `Capability` (kind = `decision` \| `generative`), `DecisionRequest`, `DecisionResult`, `DecisionExample`, and the trace envelope v2: a stable Praxis envelope, an opaque host partition key, an opaque payload. |
| **ports** | Seven `Protocol`s: `DecisionModel`, `Teacher`, `Calibrator`, `Trainer`, `TraceSink`, `SchemaValidator`, `Registry`, plus the sibling `GenerativeModel`. One fake per port ships in `praxis_core.providers.fake`. |
| **router** | `DecisionRouter` and `GenerativeRouter`: eight steps per call: policy, timed and bounded System-1 call, calibrate, validate, serve or abstain, teacher for the rest (everything, in shadow), record. Plus `observe()`: the app's own answer becomes the trace. |
| **calibrator** | One temperature per (question type, option count) for distributions; a Platt map for a scalar confidence. Both fitted on traces that carry both answers. No gradients, no dependency. |
| **sinks** | JSONL and SQLite, and a background queue in front of either. All round-trip the envelope and read back by capability. |
| **baseline** | The nearest-neighbour student behind the `DecisionModel` port: a distribution from similarity-weighted votes, the best similarity kept as `native_confidence`. Exists so the loop is demonstrably closed and a real model has a number to beat. |
| **seam, gate, student, evaluate** | The original modules, kept for the generative path: the four-check gate, the confident-wrong metric, and a `LoraStudent` whose `fit` raises until a backend is wired in. |

## Ports and adapters

| Port | Today | Planned (see [ROADMAP.md](ROADMAP.md)) |
|---|---|---|
| `DecisionModel` | `fake`, `nearest-neighbour`, the chat-completions adapter (self-reported probabilities) | a local Apple-Silicon decision model, then a PyTorch one, a read-out layer over any open LLM, an HTTP adapter for the hosted decision API |
| `GenerativeModel` | `fake`, `nearest-neighbour-generative`, the chat-completions adapter | a LoRA-tuned small model, after 1.0 |
| `Teacher` | `fake`, the chat-completions adapter (any local server or proxy) | a first-party frontier adapter, after 1.0 |
| `Calibrator` / `ScalarCalibrator` | `temperature`, `platt` | isotonic |
| `Trainer` | `fake` | temperature refit, a closed-form head, the published fine-tuning path |
| `TraceSink` | `jsonl`, `sqlite`, `queued`, `fake` | Postgres, object store |
| `SchemaValidator` | `dict-of-types` | Pydantic, JSON Schema |
| `Registry` | `fake` | a local JSON manifest |

The core promises the contract, not an adapter. The package is standard library only;
each adapter beyond the two that ship with it is a pip extra.

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
| [v1.0 release plan](docs/release-plan-v1.0.md) | What the MVP is, what waits, and the gates |
| [Changelog](CHANGELOG.md) | What changed in each version |
| [Distillation](docs/distillation.md) | The generative path: wiring a LoRA student, and what to measure first |
| [Contributing](CONTRIBUTING.md) | Running the checks, and what a change needs |

## Status

Version **0.3.0**, the first milestone of the [v1.0 plan](docs/release-plan-v1.0.md).
Python 3.11+, standard library only at runtime. **163 tests**, run by CI on 3.11 to
3.14; `mypy --strict` on everything but the legacy modules. Distribution `praxis-core`,
import `praxis_core`, command `praxis`; not on PyPI yet. Next: 0.4.0, trust the data and
the eval ([ROADMAP.md](ROADMAP.md)).

## Licence

Apache 2.0.
