# Roadmap

Every planned feature has an ID, a status and, once someone takes it, an owner. **This
file is the source of truth for what is being worked on.** Pick from here, and update
the row when you start and when you finish — see [Picking a feature](#picking-a-feature).

The target is **v1.0, the MVP** defined in [docs/release-plan-v1.0.md](docs/release-plan-v1.0.md):
capture what the app's main model does, curate it, fit a small student of any kind
without a GPU, measure it, ask Praxis whether it is ready, and serve it behind
confidence routing with the main model as the permanent fallback. Releases 0.3.0 to
0.6.0 are the milestones on the way; everything under "After 1.0" waits.

## Status

| Status | Means | Who moves it on |
|---|---|---|
| **Proposed** | an idea; the scope is not agreed yet | a maintainer, to Ready or Needs decision |
| **Needs decision** | a design choice must be made first — usually a contract or port change | a maintainer, after discussion on the issue |
| **Ready** | scope and acceptance agreed; anyone may pick it | you, when you claim it |
| **In progress** | claimed — the row names the owner and the date | the owner, when the pull request opens |
| **In review** | a pull request is open | a maintainer, when it merges |
| **Done** | merged; the row names the version | — |

Priority: **P0** a correctness bug, fix first · **P1** the next release · **P2** planned ·
**P3** an idea. Size: **S** about a day · **M** a few days · **L** a week or more, and
worth splitting.

## Picking a feature

1. **Choose a `Ready` row.** New here? Take one marked *good first issue*.
2. **Claim it.** Open an issue with the *Claim a feature* template naming the ID, or
   comment on the feature's issue if one exists. A maintainer confirms within a few days.
3. **Mark it `In progress`** in this file — your handle and the date in the last
   column — in your first pull request, or in a one-line pull request of its own.
4. **For an L-sized feature, write a design note first**, from
   [the template](docs/features/TEMPLATE.md), and get it agreed on the issue before the
   code.
5. **Open the pull request.** Set the row to `In review`, and meet the acceptance
   criteria below — each one is a test. [Contributing](CONTRIBUTING.md) has what every
   change needs.
6. **On merge,** the row becomes `Done` with the version.

One feature per person at a time. A claim with no visible progress for 21 days goes back
to `Ready`, so nothing stays blocked by a claim nobody is working on. To propose
something new, open an issue with the *Propose a feature* template; it gets an ID when
accepted.

## Features

### 0.2.0 — the redesign lands (done)

| ID | Feature | Area | P | Size | Status | Owner, or release when done |
|---|---|---|---|---|---|---|
| PX-001 | [Contracts: typed questions, request, result, envelope v2, seven ports](#px-001) | core | P0 | M | Done | 0.2.0.dev0 |
| PX-002 | [Router with abstain, shadow and canary; the trace path never raises](#px-002) | router | P0 | M | Done | 0.2.0.dev0 |
| PX-003 | [Temperature calibrator per (question type, option count)](#px-003) | calibrate | P0 | S | Done | 0.2.0.dev0 |
| PX-004 | [JSONL and SQLite trace sinks](#px-004) | trace | P1 | S | Done | 0.2.0.dev0 |
| PX-005 | [Nearest-neighbour baseline behind the `DecisionModel` port](#px-005) | baseline | P1 | S | Done | 0.2.0.dev0 |
| PX-006 | [`praxis demo`: `support.triage` end to end in under a second](#px-006) | cli | P1 | S | Done | 0.2.0.dev0 |

### 0.3.0 — capture, and both capability kinds (M1)

| ID | Feature | Area | P | Size | Status | Owner, or release when done |
|---|---|---|---|---|---|---|
| PX-100 | [Observe-mode capture: the app's own answer becomes the trace](#px-100) | capture | P0 | M | Done | 0.3.0 |
| PX-101 | [Background sink: capture adds no visible latency](#px-101) | trace | P0 | S | Done | 0.3.0 |
| PX-070 | [Generative capabilities through the same router](#px-070) | router | P0 | M | Done | 0.3.0 |
| PX-080 | [Scalar confidence calibrator (Platt)](#px-080) | calibrate | P1 | S | Done | 0.3.0 |
| PX-104 | [A generative example capability beside `support.triage`](#px-104) | demo | P1 | S | Done | 0.3.0 |
| PX-024 | [OpenAI-compatible local adapter: student, System-1 and teacher](#px-024) | providers | P1 | M | Done | 0.3.0 |
| PX-028 | [pip extras per adapter, dependencies imported lazily](#px-028) | packaging | P1 | S | Done | 0.3.0 |

### 0.3.2 — the first public release

Found by the first outside review of the committed tree (2026-10-01). One row at a time.

| ID | Feature | Area | P | Size | Status | Owner, or release when done |
|---|---|---|---|---|---|---|
| PX-900 | [Safe by default: shadow stage, calibration required](#px-900) | router | P0 | S | Done | 0.3.2 |
| PX-901 | [Readiness gate: `set_stage` refuses canary and serve until the verdict is ready](#px-901) | router | P1 | S | Done | 0.3.2 |
| PX-902 | [Remove the v0.1 modules; docs match the code; the demo picture is real output](#px-902) | docs | P1 | S | Done | 0.3.2 |

### 0.4.0 — trust the data, trust the eval (M2)

| ID | Feature | Area | P | Size | Status | Owner, or release when done |
|---|---|---|---|---|---|---|
| PX-040 | [Gate checks for decision traces](#px-040) | gate | P1 | S | Ready | |
| PX-041 | [Decision dataset builder: split, decontamination report, manifest](#px-041) | data | P1 | L | Ready | |
| PX-030 | [Decision scorecard: paired accuracy with McNemar and bootstrap CI](#px-030) | eval | P1 | M | Ready | |
| PX-031 | [Calibration error before and after, per question type](#px-031) | eval | P1 | S | Ready | |
| PX-032 | [Selective-risk curve and the operating point](#px-032) | eval | P1 | M | Ready | |
| PX-033 | [Confident-wrong, abstain rate, latency and cost per thousand calls](#px-033) — *good first issue* | eval | P1 | S | Ready | |
| PX-034 | [`praxis eval`: deterministic, with a teacher-versus-teacher sanity check](#px-034) | cli | P1 | M | Ready | |

### 0.5.0 — registry, promotion, status (M3)

| ID | Feature | Area | P | Size | Status | Owner, or release when done |
|---|---|---|---|---|---|---|
| PX-044 | [Local JSON registry, `praxis promote` and `praxis rollback`](#px-044) | registry | P1 | M | Ready | |
| PX-110 | [`praxis status`: funnel, readiness verdict, offload share, capacity](#px-110) | cli | P0 | M | Ready | |
| PX-026 | [`praxis doctor`](#px-026) | cli | P1 | M | Ready | |
| PX-027 | [Adapter conformance suite](#px-027) | tests | P1 | M | Ready | |
| PX-045 | [`praxis trace`, `build-dataset`, `calibrate`, `fit`](#px-045) | cli | P2 | M | Ready | |

### 0.6.0 — students and training rungs A and B (M4)

| ID | Feature | Area | P | Size | Status | Owner, or release when done |
|---|---|---|---|---|---|---|
| PX-020 | [Apple-Silicon decision-model adapter (`laya-mlx`)](#px-020) | providers | P1 | M | Ready | |
| PX-042 | [`temperature-refit` trainer](#px-042) — *good first issue* | train | P1 | S | Ready | |
| PX-111 | [Exemplar trainer: a small LLM learns from retrieved captured examples](#px-111) | train | P1 | M | Ready | |
| PX-112 | [`praxis suggest`: the student catalogue, metadata only](#px-112) | cli | P1 | M | Ready | |
| PX-046 | [Outcome and feedback as late-bound labels](#px-046) | data | P1 | M | Needs decision | |

### 1.0.0 — release (M5)

| ID | Feature | Area | P | Size | Status | Owner, or release when done |
|---|---|---|---|---|---|---|
| PX-120 | [Host integration guide: capture from your app in ten lines](#px-120) | docs | P0 | S | Ready | |
| PX-121 | [CLI reference and README for 1.0](#px-121) | docs | P1 | S | Ready | |
| PX-122 | [One-command definition-of-done test](#px-122) | tests | P0 | M | Ready | |
| PX-123 | [First-run audit: a stranger clones, runs, reads](#px-123) — *good first issue* | docs | P0 | S | Ready | |
| PX-124 | [Decision log, linter, formatter, `make check`](#px-124) | docs | P0 | S | Done | 0.3.1 |
| PX-090 | [Publish to PyPI](#px-090) | distribution | P0 | S | Ready | |

### After 1.0

| ID | Feature | Area | P | Size | Status | Owner, or release when done |
|---|---|---|---|---|---|---|
| PX-071 | [LoRA trainer for generative students (`mlx-lm`, then `peft`)](#px-071) | train | P1 | L | Ready | |
| PX-050 | [Fine-tune trainer for the decision model, then recalibration](#px-050) | train | P2 | L | Needs decision | |
| PX-043 | [Closed-form head trainer over the read-out adapter (`anyjev-head`)](#px-043) | train | P2 | M | Ready | |
| PX-022 | [Read-out adapter over any open causal LLM (`anyjev`)](#px-022) | providers | P2 | M | Ready | |
| PX-021 | [PyTorch decision-model adapter (`laya`)](#px-021) | providers | P2 | M | Ready | |
| PX-023 | [HTTP adapter for the hosted decision API and its self-hosted twin (`systemone-http`)](#px-023) — *good first issue* | providers | P2 | S | Ready | |
| PX-025 | [Anthropic teacher](#px-025) — *good first issue* | providers | P2 | S | Ready | |
| PX-082 | [Pydantic and JSON Schema validators](#px-082) | validate | P1 | S | Ready | |
| PX-072 | [Async entry point for async hosts](#px-072) | router | P2 | M | Proposed | |
| PX-060 | [A host-side decision-provider adapter, in its own package](#px-060) | integration | P2 | S | Proposed | |
| PX-081 | [Postgres and object-store trace sink](#px-081) | trace | P3 | M | Proposed | |
| PX-083 | [Web dashboard and REST control plane](#px-083) | ui | P3 | L | Proposed | |
| PX-130 | [Synthetic and self-play generator, estimate before spend](#px-130) | data | P3 | L | Proposed | |
| PX-131 | [Sampling-based confidence for small LLMs (self-consistency)](#px-131) | calibrate | P2 | M | Proposed | |

## Details

Each entry says what is wrong or missing today, what done looks like, and where in the
code it starts. Every acceptance line is a test.

### 0.2.0 — the redesign lands

<a id="px-001"></a>**PX-001 — Contracts.** *Done in* `praxis_core/contracts.py`,
`praxis_core/ports.py`, `praxis_core/providers/fake.py`: every contract round-trips through
dict and JSON; the fakes satisfy the ports; the core imports only the standard library;
no provider name outside `praxis_core/providers/`; `mypy --strict` is clean.

<a id="px-002"></a>**PX-002 — Router.** *Done in* `praxis_core/router.py`: a System-1
error, timeout, every malformed mode, a misbehaving calibrator and a missing model are
abstentions with a reason; 100 hostile calls are 100 % served by System-2; shadow
records both answers; a sink that raises is counted, not raised.

<a id="px-003"></a>**PX-003 — Temperature calibrator.** *Done in*
`praxis_core/calibrate.py`: an over-confident model fits to `T > 1`, an under-confident
one to `T < 1`, per (type, option count), with lower negative log-likelihood and
calibration error on held-out traces; an unfitted group is the identity and says so.

<a id="px-004"></a>**PX-004 — Sinks.** *Done in* `praxis_core/trace.py`: both sinks
round-trip the envelope, filter by capability, keep the latest version of a re-recorded
trace, and the demo writes to each.

<a id="px-005"></a>**PX-005 — Baseline.** *Done in* `praxis_core/baseline.py`,
`praxis_core/dataset.py`: unfitted it is uniform and never served; fitted it reproduces
what it has seen with the best similarity kept as `native_confidence`; a hash mismatch
is reported, not learned.

<a id="px-006"></a>**PX-006 — Demo.** *Done in* `praxis_core/demo.py`, `praxis_core/cli.py`: four
stages, deterministic for a seed, under a second, runs in CI with nothing installed.

### 0.3.0 — capture, and both capability kinds

<a id="px-100"></a>**PX-100 — Observe-mode capture.** Today Praxis must make the System-2
call itself. The original design's wedge is the other way round: the app keeps calling
its own model and hands Praxis the result (§01 A.8, §04 S1/S2). *Done when:* the router
gains `observe(request, answer, info, latency_ms, cost_usd)` for both kinds; the app's
answer is validated and recorded as System-2 with the student run in shadow when one is
configured; it never raises; a stored trace rebuilds the exact request (replay
equivalence) in a test; the demo has an observe-mode stage. *Starts in:*
`praxis_core/router.py`.

<a id="px-101"></a>**PX-101 — Background sink.** `record` writes synchronously today.
*Done when:* a queue and one daemon thread sit in front of any sink; `record` returns in
microseconds; the queue is bounded and drops are counted on the router's stats, never
raised; `flush()` exists for tests and shutdown; a test shows ≤ 5 ms added at p95 over
1,000 calls. *Starts in:* `praxis_core/trace.py`.

<a id="px-104"></a>**PX-104 — A generative example capability.** *Decided 2026-10-01:*
`support.extract` (product, issue type and order id from the same tickets). *Done when:* the demo
runs it through observe mode and the generative router with the fake student and
teacher, under the same one-second budget.

<a id="px-070"></a>**PX-070 — Generative capabilities through the same router.** The
`GenerativeModel` port is declared and `DecisionRouter` refuses generative capabilities.
*Done when:* a generative capability routes with the same stages, abstain reasons, trace
and stats; validity through the `SchemaValidator` port is the hard gate; the scalar
confidence goes through PX-080; "matched the label" is exact after normalisation by
default with a host-supplied match function allowed; the fault-injection suite passes for
the generative kind exactly as for the decision kind. *Starts in:* `praxis_core/router.py`,
`praxis_core/contracts.py` (output and schema fields on the trace).

<a id="px-080"></a>**PX-080 — Scalar confidence calibrator (Platt).** The temperature
calibrator works on distributions; a generative student reports one number. *Done
when:* a Platt calibrator (two parameters, fitted by a stdlib optimiser on (confidence,
matched) pairs) sits behind the same `Calibrator` port, is selected per capability kind,
and lowers calibration error on a synthetic over-confident student in a test.

### 0.3.2 — the first public release

<a id="px-900"></a>**PX-900 — Safe by default.** *Found 2026-10-01, P0:* `RoutingPolicy`
defaulted to `stage="serve"` and `require_calibrated=False`, so a router built with no
policy served a confident student with no calibrator, against the README's "nothing is
served uncalibrated". *Done when:* the defaults are `stage="shadow"` and
`require_calibrated=True`; a test builds a router with no policy and a student that is
always sure, and every answer comes from the teacher; the tests that want the old
behaviour say so in their policy. *Starts in:* `praxis_core/router.py`.

<a id="px-901"></a>**PX-901 — Readiness gate.** *Found 2026-10-01:* the demo printed
"stays in shadow" and then ran canary and serve anyway; `set_stage` only swapped the
policy. *Done when:* `router.readiness()` returns the verdict (shadow comparisons,
agreement, calibrator fitted, what is missing) against thresholds on the policy;
`set_stage("canary" | "serve")` raises `NotReady` naming what is missing unless
`force=True`, and forced promotions are counted; the demo stops at the gate for the
capability that is not ready; both routers are covered by tests. *Starts in:*
`praxis_core/router.py`, `praxis_core/demo.py`.

<a id="px-902"></a>**PX-902 — Docs match the code.** *Found 2026-10-01:*
`praxis_core/legacy/` said it waited for PX-070, which shipped in 0.3.0; CONTRIBUTING
named a class that no longer exists and one example capability where two ship; the demo
picture was drawn, not captured; the README's demo command needs `python3` outside a
virtual environment. *Done when:* the v0.1 modules and their tests are gone and nothing
excludes them from the checks; every doc line found above is fixed; `docs/images/demo.png`
is rendered from the real output by a script kept beside it; a test runs README steps
2 to 5 as written; the roadmap's last column is named for what it holds.

### Adapters and providers

Before writing any adapter, re-read the provider's current README: these APIs were days
old when the plan was written and move. Each adapter maps the provider's confidence into
`native_confidence`, accepts `noul` for `boolean`, lets exceptions escape, and is a pip
extra whose dependency is imported lazily (PX-028).

<a id="px-020"></a>**PX-020 — Apple-Silicon decision-model adapter (`laya-mlx`).** The
first real System-1: the open-weights encoder decision model on Apple MLX, single-digit
milliseconds per decision on a laptop. *Done when:* `pip install "praxis[laya-mlx]"`
makes `python -m praxis_core demo --system1 laya-mlx` run the same four stages with the real
model; the conformance suite (PX-027) passes; `praxis doctor` reports it. *Starts in:*
`praxis_core/providers/laya_mlx.py`, `praxis_core/cli.py`.

<a id="px-021"></a>**PX-021 — PyTorch decision-model adapter (`laya`).** The same model
family on PyTorch, for machines without Apple Silicon and for Rung C. *Done when:* the
conformance suite passes; a request that exceeds the model's option-text token budget is
refused by `doctor` before runtime, not at runtime. *Starts in:* `praxis_core/providers/laya.py`.

<a id="px-022"></a>**PX-022 — Read-out adapter over any open causal LLM (`anyjev`).**
Typed decisions read from a local LLM's next-token distribution, no training needed at
its level 0. *Done when:* the conformance suite passes over a small local model; the
adapter's level (`raw`, `L0`, `L1`, `L2`) is recorded in `ModelInfo.level`; its
26-option cap is a `doctor` refusal. *Starts in:* `praxis_core/providers/anyjev.py`.

<a id="px-023"></a>**PX-023 — HTTP adapter for the hosted decision API and its
self-hosted twin (`systemone-http`).** One adapter, since the self-hosted server's
response is schema-identical to the hosted one. *Done when:* the conformance suite passes
against a recorded fixture and against a live endpoint when a key is present; a timeout
is an abstention. *Starts in:* `praxis_core/providers/systemone_http.py`, standard-library
`urllib` only.

<a id="px-024"></a>**PX-024 — OpenAI-compatible local adapter: student, System-1 and teacher.**
One class over the wire protocol that local servers, proxies and the hosted API share
(verified on a local Ollama this session: a strict JSON schema with string-enum,
integer-enum and boolean fields was honoured). Three roles from one request shape: a
`GenerativeModel` student (output against the schema plus a self-reported confidence),
a `DecisionModel` for choice / score / boolean (self-reported probabilities, calibrated
by Praxis; no log-probabilities in 1.0), and a `Teacher`. *Done when:* offline tests run
against a stdlib fake HTTP server (refusal, malformed body, 500); a live test runs against
a local server only when `PRAXIS_LIVE=1`; the demo runs with `--student` and `--teacher`
pointing at it. *Starts in:* `praxis_core/providers/openai_compat.py`; design note
[docs/features/PX-024-openai-compatible-teacher.md](docs/features/PX-024-openai-compatible-teacher.md).

<a id="px-025"></a>**PX-025 — Anthropic teacher.** As PX-024, with the provider's own
structured-output mechanism. *Starts in:* `praxis_core/providers/anthropic.py`.

<a id="px-026"></a>**PX-026 — `praxis doctor`.** Nothing today says what is installed or
reachable. *Done when:* `praxis doctor` lists every adapter with installed / importable /
reachable, and refuses, per capability, a provider that cannot serve its option count or
question types before any request is made. *Starts in:* `praxis_core/cli.py`,
`praxis_core/providers/__init__.py` (a registry of adapters and their limits).

<a id="px-027"></a>**PX-027 — Adapter conformance suite.** *Done when:* one test module
runs the same requests through every installed adapter and asserts the same result
shape, valid distributions, `native_confidence` set, `noul` accepted, and exceptions
surfaced as abstentions through the router; skipped, not failed, where an adapter is not
installed. *Starts in:* `tests/conformance.py`, parameterised by the fakes first.

<a id="px-028"></a>**PX-028 — pip extras per adapter.** *Done when:* `pyproject.toml`
declares one extra per adapter; `import praxis_core.providers` pulls no vendor SDK; importing
an adapter without its extra raises a message naming the extra to install.

### 0.4.0 — trust the data, trust the eval

<a id="px-030"></a>**PX-030 — Decision scorecard.** Today there is no scorecard: the
demo counts confident-wrong itself, and nothing compares two students on the same inputs. *Done when:* per capability and per question type, accuracy
against the System-2 label is paired with McNemar's test and a bootstrap confidence
interval; two runs on the same inputs are identical. *Starts in:*
`praxis_core/evaluate.py`, standard library only.

<a id="px-031"></a>**PX-031 — Calibration error before and after.** *Done when:* the
scorecard reports expected calibration error per question type with and without the
fitted calibrator, from `expected_calibration_error` in `praxis_core/calibrate.py`.

<a id="px-032"></a>**PX-032 — Selective-risk curve.** *Done when:* error rate versus
share served by System-1 as the threshold sweeps, and the chosen operating point, are in
the scorecard and printable as a table.

<a id="px-033"></a>**PX-033 — Confident-wrong, abstain rate, latency and cost.**
*Done when:* the scorecard carries confident-wrong rate, abstain rate, and latency and
cost per thousand calls for System-1 and System-2, from the trace envelope alone.

<a id="px-034"></a>**PX-034 — `praxis eval`.** *Done when:* `praxis eval <traces>` prints
the scorecard; a teacher-versus-teacher run yields a win rate near 0.5 with an interval
spanning zero; the promotion rules (hard gates are vetoes, no stratum regresses,
calibration error above 0.10 blocks raising the share) are applied and reported.

### Data, registry and training rungs

<a id="px-040"></a>**PX-040 — Gate checks for decision traces.** Today the dataset builder
skips traces by reason (not a label candidate, no System-2 answer, question hash
mismatch, other capability), but no gate checks a trace's content before it is used. *Done when:* a decision trace is refused
when the answer is outside the declared set, the distribution does not sum to one, or
the question hash does not match the capability, each with a counted reason; outcome
and feedback labels, when present, outrank the System-2 label.

<a id="px-041"></a>**PX-041 — Decision dataset builder.** `examples_from_traces` builds
examples and reports skips. *Done when:* group-aware splitting by `input_key` and host
partition, a decontamination report (held-out examples that also appear in training),
and a versioned manifest with lineage back to trace ids; two builds from the same traces
are identical. Write a design note first.

<a id="px-042"></a>**PX-042 — `temperature-refit` trainer.** *Done when:* the `Trainer`
port has a stdlib implementation that refits the calibrator on a dataset version and
returns a `ModelArtifact` whose metrics carry the before and after calibration error.

<a id="px-043"></a>**PX-043 — Closed-form head trainer (`anyjev-head`).** *Done when:*
100 to 300 labels fit a head in seconds through the read-out adapter, the artifact is
registered, and the scorecard improves over level 0 on the demo capability.

<a id="px-044"></a>**PX-044 — Local JSON registry and `praxis promote`.** *Done when:*
artifacts, their stage and a manifest per capability live in one JSON file; `praxis
promote` moves a version from shadow to canary to serve only when the scorecard clears
the gates, and refuses with the failing gate named.

<a id="px-045"></a>**PX-045 — The rest of the CLI.** `init` (a project skeleton with the
demo capability), `trace` (tail and count), `build-dataset`, `calibrate`, `train`.

<a id="px-046"></a>**PX-046 — Outcome and feedback as late-bound labels.** The envelope
has `outcome` and `feedback`; nothing writes them. *Decision needed:* the
`record_outcome(trace_id, ...)` API and how an outcome-derived label is expressed per
question type.

### Fine-tuning (after 1.0)

<a id="px-050"></a>**PX-050 — Fine-tune trainer.** The published fine-tuning path for
the encoder decision model, wrapped as a reproducible job, then recalibration.
*Decision needed:* whether the Apple-Silicon runtime supports training or only
inference, and whether the PyTorch path trains on Apple MPS at acceptable speed; the
plan accepts that this may be a cloud-notebook step for Apple users. *Done when:* the
fine-tuned model beats Rung B on the held-out set with a confidence interval and no
stratum regresses.

### 0.5.0 — registry, promotion, status

<a id="px-110"></a>**PX-110 — `praxis status`.** The question the owner asks: is this
student ready, what share can it take, how much traffic can it hold. *Done when:* from
the sink and the registry it prints the funnel (captured → gated → labelled), shadow
agreement, calibration error, confident-wrong rate, the offload share at the current
threshold, latency p50 and p95 for student and teacher, a throughput floor (one worker at
p50, stated as a floor), and a verdict (`shadow` / `canary` / `serve`) against the v1.0
gates with every missing item named ("need 140 more labels"); fixtures cover each
verdict. *Starts in:* `praxis_core/cli.py`, `praxis_core/evaluate.py`. The verdict itself
exists since 0.3.2: `router.readiness()` (PX-901); `status` reads it for a running system
from the sink instead of a live router.

### 0.6.0 — students and training rungs

<a id="px-111"></a>**PX-111 — Exemplar trainer.** Rung 0 of the original ladder: "fit"
indexes the captured examples; at serve time the k most similar captured (input →
output) pairs are the demonstrations in the small LLM's prompt. *Done when:* a `Trainer`
produces a `ModelArtifact` that the OpenAI-compatible adapter loads; on the demo
capability the scorecard with exemplars beats zero-shot; k and the similarity are
recorded in the artifact. *Starts in:* `praxis_core/learning/exemplar.py`.

<a id="px-112"></a>**PX-112 — `praxis suggest`.** *Done when:* a JSON catalogue inside
the package lists, per capability shape, the student types that fit, the runtime, size,
licence, the Praxis rungs that apply, how to install, and a `verified_on` date; `praxis
suggest <capability>` prints the matching entries; every entry was checked against its
README on the date shown; no weights are shipped or downloaded by the command.

### 1.0.0 — release

<a id="px-120"></a>**PX-120 — Host integration guide.** *Done when:* `docs/integration.md`
shows capture from an existing app in ten lines for both kinds, the migration stages
(observe → shadow student → canary → serve), what the app must supply, and what it
never has to change.

<a id="px-121"></a>**PX-121 — CLI reference and README for 1.0.** Every command, every
flag, one example each; the README demo output refreshed from a real run.

<a id="px-123"></a>**PX-123 — First-run audit.** Before every release someone who did not
build it clones the repository, runs `python -m praxis_core demo` and `make check`, reads
the README top to bottom, and writes down everything that confused them. *Done when:*
the list is empty or every item has a fix or a roadmap row. Repeats per release.

<a id="px-124"></a>**PX-124 — Decision log, linter, formatter, `make check`.** *Done in*
0.3.1: `docs/decisions.md`, ruff (lint and format) in `pyproject.toml` and CI, a Makefile
whose `check` target is what CI runs.

<a id="px-122"></a>**PX-122 — One-command definition-of-done test.** *Done when:* one test
runs capture → gate → build-dataset → fit → eval → promote → serve on the demo capability
with the fakes and asserts every gate in [docs/release-plan-v1.0.md](docs/release-plan-v1.0.md) §2.

### After 1.0

<a id="px-130"></a>**PX-130 — Synthetic and self-play generator.** The original's
cold-start tool, with estimate-before-spend; deferred because production capture needs
no cold start (original §06 §6.10).

<a id="px-131"></a>**PX-131 — Sampling-based confidence for small LLMs.** N samples per
call give an empirical distribution when self-report proves uncalibrated; N times the
cost, so only if `status` shows calibration error above 0.10 after Platt.

<a id="px-060"></a>**PX-060 — A host-side decision-provider adapter.** A host that has
its own decision-provider interface gets a thin mapping package that depends on Praxis,
never the reverse. Blocked until that host's interface exists.

<a id="px-071"></a>**PX-071 — LoRA trainer for generative students.** Rung 1 of the original
ladder: fine-tune a small base on the dataset with `mlx-lm` on Apple Silicon, then
`peft` elsewhere; serve the adapter through the OpenAI-compatible adapter. The first
feature after 1.0, because it needs GPU time and a serving step, and the loop is proven
without it. Design note: [docs/features/PX-071-lora-trainer.md](docs/features/PX-071-lora-trainer.md).

<a id="px-072"></a>**PX-072 — Async entry point.** `decide()` is synchronous and bounds
System-1 with a thread. *Done when:* `adecide()` awaits async adapters end to end with
the same guarantees, proven by the same fault-injection tests.

<a id="px-081"></a>**PX-081 — Postgres and object-store trace sink.** The envelope in a
table, payloads in object storage keyed by trace id, as an optional sink.

<a id="px-082"></a>**PX-082 — Pydantic and JSON Schema validators.** Behind
`SchemaValidator`; a host's schema crosses as a reference, never as a type.

<a id="px-083"></a>**PX-083 — Web dashboard and REST control plane.** Deliberately not in
v1; the CLI and JSON artifacts are the interface until the loop is proven.

<a id="px-090"></a>**PX-090 — Publish to PyPI.** **Verified** 2026-09-30: `praxis` and
`praxis-ai` are taken on PyPI; `praxis-core` and `praxis-learning` are free. *Decided 2026-09-30:* distribution `praxis-core`, import `praxis_core`, command `praxis`; the rename landed 2026-10-01.
*Done when:* trusted publishing from the release workflow; `pip install <name>` on a clean
machine runs `python -m praxis_core demo`.
