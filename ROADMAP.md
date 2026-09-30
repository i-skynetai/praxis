# Roadmap

Every planned feature has an ID, a status and, once someone takes it, an owner. **This
file is the source of truth for what is being worked on.** Pick from here, and update
the row when you start and when you finish — see [Picking a feature](#picking-a-feature).

The plan behind it: Praxis keeps capture → gate → train → evaluate → route with a
permanent fallback, and makes the student a System-1 decision model behind a
provider-neutral port. Phases 0 and 1 are done; the rows below are the rest, in the
order the plan says to build them: providers, then evaluation, then data and the first
training rungs, then fine-tuning.

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
3. **Mark it `In progress`** in this file — your handle and the date in the Owner
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

### 0.2.0 — the redesign lands

| ID | Feature | Area | P | Size | Status | Owner |
|---|---|---|---|---|---|---|
| PX-001 | [Contracts: typed questions, request, result, envelope v2, seven ports](#px-001) | core | P0 | M | Done | 0.2.0.dev0 |
| PX-002 | [Router with abstain, shadow and canary; the trace path never raises](#px-002) | router | P0 | M | Done | 0.2.0.dev0 |
| PX-003 | [Temperature calibrator per (question type, option count)](#px-003) | calibrate | P0 | S | Done | 0.2.0.dev0 |
| PX-004 | [JSONL and SQLite trace sinks](#px-004) | trace | P1 | S | Done | 0.2.0.dev0 |
| PX-005 | [Nearest-neighbour baseline behind the `DecisionModel` port](#px-005) | baseline | P1 | S | Done | 0.2.0.dev0 |
| PX-006 | [`praxis demo`: `support.triage` end to end in under a second](#px-006) | cli | P1 | S | Done | 0.2.0.dev0 |

### 0.3.0 — providers

| ID | Feature | Area | P | Size | Status | Owner |
|---|---|---|---|---|---|---|
| PX-020 | [Apple-Silicon decision-model adapter (`laya-mlx`)](#px-020) | providers | P1 | M | Ready | |
| PX-021 | [PyTorch decision-model adapter (`laya`)](#px-021) | providers | P1 | M | Ready | |
| PX-022 | [Read-out adapter over any open causal LLM (`anyjev`)](#px-022) | providers | P1 | M | Ready | |
| PX-023 | [HTTP adapter for the hosted decision API and its self-hosted twin (`systemone-http`)](#px-023) — *good first issue* | providers | P2 | S | Ready | |
| PX-024 | [OpenAI-compatible teacher](#px-024) | providers | P1 | M | Ready | |
| PX-025 | [Anthropic teacher](#px-025) — *good first issue* | providers | P2 | S | Ready | |
| PX-026 | [`praxis doctor`](#px-026) | cli | P1 | M | Ready | |
| PX-027 | [Adapter conformance suite](#px-027) | tests | P1 | M | Ready | |
| PX-028 | [pip extras per adapter, dependencies imported lazily](#px-028) | packaging | P1 | S | Ready | |

### 0.4.0 — evaluation

| ID | Feature | Area | P | Size | Status | Owner |
|---|---|---|---|---|---|---|
| PX-030 | [Decision scorecard: paired accuracy with McNemar and bootstrap CI](#px-030) | eval | P1 | M | Ready | |
| PX-031 | [Calibration error before and after, per question type](#px-031) | eval | P1 | S | Ready | |
| PX-032 | [Selective-risk curve and the operating point](#px-032) | eval | P1 | M | Ready | |
| PX-033 | [Confident-wrong, abstain rate, latency and cost per thousand calls](#px-033) — *good first issue* | eval | P1 | S | Ready | |
| PX-034 | [`praxis eval`: deterministic, with a teacher-versus-teacher sanity check](#px-034) | cli | P1 | M | Ready | |

### 0.5.0 — data and Rungs A and B

| ID | Feature | Area | P | Size | Status | Owner |
|---|---|---|---|---|---|---|
| PX-040 | [Gate checks for decision traces](#px-040) | gate | P1 | S | Ready | |
| PX-041 | [Decision dataset builder: split, decontamination report, manifest](#px-041) | data | P1 | L | Ready | |
| PX-042 | [`temperature-refit` trainer](#px-042) — *good first issue* | train | P1 | S | Ready | |
| PX-043 | [Closed-form head trainer over the read-out adapter (`anyjev-head`)](#px-043) | train | P1 | M | Ready | |
| PX-044 | [Local JSON registry and `praxis promote`](#px-044) | registry | P1 | M | Ready | |
| PX-045 | [`praxis init`, `trace`, `build-dataset`, `calibrate`, `train`](#px-045) | cli | P2 | M | Ready | |
| PX-046 | [Outcome and feedback as late-bound labels](#px-046) | data | P2 | M | Needs decision | |

### 0.6.0 — Rung C

| ID | Feature | Area | P | Size | Status | Owner |
|---|---|---|---|---|---|---|
| PX-050 | [Fine-tune trainer as a reproducible job, then recalibration](#px-050) | train | P2 | L | Needs decision | |

### Later

| ID | Feature | Area | P | Size | Status | Owner |
|---|---|---|---|---|---|---|
| PX-060 | [A host-side decision-provider adapter, in its own package](#px-060) | integration | P2 | S | Proposed | |
| PX-070 | [Generative capabilities through the same router policy](#px-070) | router | P2 | M | Proposed | |
| PX-071 | [LoRA trainer for generative students](#px-071) | train | P3 | L | Proposed | |
| PX-072 | [Async entry point for async hosts](#px-072) | router | P2 | M | Proposed | |
| PX-080 | [Platt and isotonic calibrators](#px-080) | calibrate | P3 | S | Proposed | |
| PX-081 | [Postgres and object-store trace sink](#px-081) | trace | P3 | M | Proposed | |
| PX-082 | [Pydantic and JSON Schema validators](#px-082) | validate | P3 | S | Proposed | |
| PX-083 | [Web dashboard and REST control plane](#px-083) | ui | P3 | L | Proposed | |
| PX-090 | [Publish to PyPI](#px-090) | distribution | P1 | S | Needs decision | |

## Details

Each entry says what is wrong or missing today, what done looks like, and where in the
code it starts. Every acceptance line is a test.

### 0.2.0 — the redesign lands

<a id="px-001"></a>**PX-001 — Contracts.** *Done in* `praxis/core/contracts.py`,
`praxis/core/ports.py`, `praxis/providers/fake.py`: every contract round-trips through
dict and JSON; the fakes satisfy the ports; the core imports only the standard library;
no provider name outside `praxis/providers/`; `mypy --strict` is clean.

<a id="px-002"></a>**PX-002 — Router.** *Done in* `praxis/core/router.py`: a System-1
error, timeout, every malformed mode, a misbehaving calibrator and a missing model are
abstentions with a reason; 100 hostile calls are 100 % served by System-2; shadow
records both answers; a sink that raises is counted, not raised.

<a id="px-003"></a>**PX-003 — Temperature calibrator.** *Done in*
`praxis/core/calibrate.py`: an over-confident model fits to `T > 1`, an under-confident
one to `T < 1`, per (type, option count), with lower negative log-likelihood and
calibration error on held-out traces; an unfitted group is the identity and says so.

<a id="px-004"></a>**PX-004 — Sinks.** *Done in* `praxis/core/trace.py`: both sinks
round-trip the envelope, filter by capability, keep the latest version of a re-recorded
trace, and the demo writes to each.

<a id="px-005"></a>**PX-005 — Baseline.** *Done in* `praxis/core/baseline.py`,
`praxis/core/dataset.py`: unfitted it is uniform and never served; fitted it reproduces
what it has seen with the best similarity kept as `native_confidence`; a hash mismatch
is reported, not learned.

<a id="px-006"></a>**PX-006 — Demo.** *Done in* `praxis/demo.py`, `praxis/cli.py`: four
stages, deterministic for a seed, under a second, runs in CI with nothing installed.

### 0.3.0 — providers

Before writing any adapter, re-read the provider's current README: these APIs were days
old when the plan was written and move. Each adapter maps the provider's confidence into
`native_confidence`, accepts `noul` for `boolean`, lets exceptions escape, and is a pip
extra whose dependency is imported lazily (PX-028).

<a id="px-020"></a>**PX-020 — Apple-Silicon decision-model adapter (`laya-mlx`).** The
first real System-1: the open-weights encoder decision model on Apple MLX, single-digit
milliseconds per decision on a laptop. *Done when:* `pip install "praxis[laya-mlx]"`
makes `python -m praxis demo --system1 laya-mlx` run the same four stages with the real
model; the conformance suite (PX-027) passes; `praxis doctor` reports it. *Starts in:*
`praxis/providers/laya_mlx.py`, `praxis/cli.py`.

<a id="px-021"></a>**PX-021 — PyTorch decision-model adapter (`laya`).** The same model
family on PyTorch, for machines without Apple Silicon and for Rung C. *Done when:* the
conformance suite passes; a request that exceeds the model's option-text token budget is
refused by `doctor` before runtime, not at runtime. *Starts in:* `praxis/providers/laya.py`.

<a id="px-022"></a>**PX-022 — Read-out adapter over any open causal LLM (`anyjev`).**
Typed decisions read from a local LLM's next-token distribution, no training needed at
its level 0. *Done when:* the conformance suite passes over a small local model; the
adapter's level (`raw`, `L0`, `L1`, `L2`) is recorded in `ModelInfo.level`; its
26-option cap is a `doctor` refusal. *Starts in:* `praxis/providers/anyjev.py`.

<a id="px-023"></a>**PX-023 — HTTP adapter for the hosted decision API and its
self-hosted twin (`systemone-http`).** One adapter, since the self-hosted server's
response is schema-identical to the hosted one. *Done when:* the conformance suite passes
against a recorded fixture and against a live endpoint when a key is present; a timeout
is an abstention. *Starts in:* `praxis/providers/systemone_http.py`, standard-library
`urllib` only.

<a id="px-024"></a>**PX-024 — OpenAI-compatible teacher.** Covers local servers and
proxies that speak the same API. *Done when:* a `DecisionRequest` becomes one
structured-output call, the typed answers are validated against the declared set, and a
provider distribution is captured when exposed (log-probabilities); a recorded fixture
runs in CI. *Starts in:* `praxis/providers/openai_compat.py`.

<a id="px-025"></a>**PX-025 — Anthropic teacher.** As PX-024, with the provider's own
structured-output mechanism. *Starts in:* `praxis/providers/anthropic.py`.

<a id="px-026"></a>**PX-026 — `praxis doctor`.** Nothing today says what is installed or
reachable. *Done when:* `praxis doctor` lists every adapter with installed / importable /
reachable, and refuses, per capability, a provider that cannot serve its option count or
question types before any request is made. *Starts in:* `praxis/cli.py`,
`praxis/providers/__init__.py` (a registry of adapters and their limits).

<a id="px-027"></a>**PX-027 — Adapter conformance suite.** *Done when:* one test module
runs the same requests through every installed adapter and asserts the same result
shape, valid distributions, `native_confidence` set, `noul` accepted, and exceptions
surfaced as abstentions through the router; skipped, not failed, where an adapter is not
installed. *Starts in:* `tests/conformance.py`, parameterised by the fakes first.

<a id="px-028"></a>**PX-028 — pip extras per adapter.** *Done when:* `pyproject.toml`
declares one extra per adapter; `import praxis.providers` pulls no vendor SDK; importing
an adapter without its extra raises a message naming the extra to install.

### 0.4.0 — evaluation

<a id="px-030"></a>**PX-030 — Decision scorecard.** Today `praxis/evaluate.py` scores the
generative student only. *Done when:* per capability and per question type, accuracy
against the System-2 label is paired with McNemar's test and a bootstrap confidence
interval; two runs on the same inputs are identical. *Starts in:*
`praxis/core/evaluate.py`, standard library only.

<a id="px-031"></a>**PX-031 — Calibration error before and after.** *Done when:* the
scorecard reports expected calibration error per question type with and without the
fitted calibrator, from `expected_calibration_error` in `praxis/core/calibrate.py`.

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

### 0.5.0 — data and Rungs A and B

<a id="px-040"></a>**PX-040 — Gate checks for decision traces.** The four-check gate in
`praxis/gate.py` knows only generative traces. *Done when:* a decision trace is refused
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

### 0.6.0 — Rung C

<a id="px-050"></a>**PX-050 — Fine-tune trainer.** The published fine-tuning path for
the encoder decision model, wrapped as a reproducible job, then recalibration.
*Decision needed:* whether the Apple-Silicon runtime supports training or only
inference, and whether the PyTorch path trains on Apple MPS at acceptable speed; the
plan accepts that this may be a cloud-notebook step for Apple users. *Done when:* the
fine-tuned model beats Rung B on the held-out set with a confidence interval and no
stratum regresses.

### Later

<a id="px-060"></a>**PX-060 — A host-side decision-provider adapter.** A host that has
its own decision-provider interface gets a thin mapping package that depends on Praxis,
never the reverse. Blocked until that host's interface exists.

<a id="px-070"></a>**PX-070 — Generative capabilities through the same router policy.**
`GenerativeModel` is declared; `DecisionRouter` refuses generative capabilities. *Done
when:* a generative capability routes with the same stages, abstain and trace, with the
`SchemaValidator` as the validity check.

<a id="px-071"></a>**PX-071 — LoRA trainer for generative students.** Rung D:
`LoraStudent.fit` stops raising. See [docs/distillation.md](docs/distillation.md).

<a id="px-072"></a>**PX-072 — Async entry point.** `decide()` is synchronous and bounds
System-1 with a thread. *Done when:* `adecide()` awaits async adapters end to end with
the same guarantees, proven by the same fault-injection tests.

<a id="px-080"></a>**PX-080 — Platt and isotonic calibrators.** Behind the same port,
selected per capability, compared on calibration error.

<a id="px-081"></a>**PX-081 — Postgres and object-store trace sink.** The envelope in a
table, payloads in object storage keyed by trace id, as an optional sink.

<a id="px-082"></a>**PX-082 — Pydantic and JSON Schema validators.** Behind
`SchemaValidator`; a host's schema crosses as a reference, never as a type.

<a id="px-083"></a>**PX-083 — Web dashboard and REST control plane.** Deliberately not in
v1; the CLI and JSON artifacts are the interface until the loop is proven.

<a id="px-090"></a>**PX-090 — Publish to PyPI.** `pip install praxis`, released by
trusted publishing from the release workflow. A maintainer decision.
