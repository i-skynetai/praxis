# Praxis v1.0 — the MVP release plan

*2026-09-30. The base target for the first release. Every claim is labelled **Verified**
(where), **To verify**, or **Question** (a decision for the owner). The original design
(June 2026, private) is the frame; the September redesign is one student class inside
it; this plan says what ships first and what waits.*

## 1. What v1.0 lets a developer do

On a laptop, with no cloud and no API key:

1. **Register** a capability: a name, and either typed questions (choice / score /
   yes-no) or an output schema for text and structured output.
2. **Capture** what the app's own main model does for that capability, in production,
   with a one-line call that never fails the request. Or let Praxis make the call.
3. **Curate** those traces into a versioned, decontaminated dataset, with every skip
   reported by reason.
4. **Fit a small student of any kind** from that data without a GPU: a decision model
   plus a calibrated temperature, a small local LLM with retrieved demonstrations, or
   the nearest-neighbour baseline. Bring your own model by name, or take a suggestion.
5. **Measure it honestly**: paired against the main model's answers on identical inputs,
   with calibration error, confident-wrong rate, the share of traffic it would carry at
   a threshold, latency and cost.
6. **Ask Praxis** whether it is ready, what share it can take, what is still missing, and
   roughly how much traffic it can hold.
7. **Serve** it behind confidence routing, shadow → canary → serve, with the main model
   as the permanent fallback and one-flag rollback.

Fine-tuning (LoRA) is the first feature after 1.0, not in it. The loop must be trusted
before the model is optimised ("trust the loop, then trust the model", original design
§07 §7.1, **Verified**); every gradient-free rung above is a real student that learns
from recorded data, and the LoRA trainer plugs into the same `Trainer` port when it
lands.

## 2. The success bar (definition of done)

Taken from the original PoC definition (§05 §5.7, §07 §7.4, PRD §6.1, **Verified**),
scaled to the MVP. **One command on the demo capability does all of this and every gate
is a test:**

| Gate | Threshold | Source |
|---|---|---|
| Capture never fails the request; a dead sink loses nothing the caller sees | 100 % under fault injection | original H3; exists today for the router path |
| Capture adds no visible latency | ≤ 5 ms at p95 with the background sink | original Phase 1 exit |
| A captured trace is replayable | the stored trace rebuilds the exact request | original Phase 1 exit |
| Schema validity of served generative outputs | ≥ 99 % | original H1 |
| Decontamination | train ∩ eval = ∅ by content hash, reported | original H4 |
| Calibration before serving | expected calibration error ≤ 0.10 | original R4 |
| Reproducibility | two builds and two evals on the same inputs are identical | original Phase 2/3 exits |
| Readiness verdict is honest | `praxis status` says canary only when the gates above pass and ≥ 200 labelled examples exist | original §7.3 Phase 2 rule of thumb |
| Offload share is reported, not promised | the scorecard shows the share served at the chosen threshold and the confident-wrong rate on it | PRD §6.1 "safe partial offload" |
| No test needs a frontier model | the suite runs green with fakes; local-model tests are opt-in | owner's rule, 2026-09-30 |

Plus the standing checks: tests green on Python 3.11 to 3.14, `mypy --strict` clean,
standard library only in `praxis/core`, no provider name outside `praxis_core/providers/`,
the demo under one second with the fakes.

## 3. In and out

| In v1.0 | Out (roadmap, "After 1.0") | Why the line is here |
|---|---|---|
| Observe-mode capture, plus Praxis-makes-the-call | Frontier teacher adapters (OpenAI, Anthropic) | observe mode makes them unnecessary to start; no test may need them |
| Decision and generative kinds through one router | Async entry point | the sync path with a bounded thread meets the gates; async is a host convenience |
| Students: nearest-neighbour, laya-mlx, a local small LLM via Ollama | laya (PyTorch), AnyJev, the hosted decision API | one real adapter per student class proves the port; the rest are copies |
| Training rungs A and B and the exemplar rung (no gradients) | LoRA fine-tune (mlx-lm, peft), laya fine-tune, on-policy and preference rungs | needs GPU time and a serving step for the adapter; lands first after 1.0 |
| Temperature (distributions) and Platt (scalar scores) calibrators | Isotonic | two are enough to cover both student kinds |
| Gate, dataset builder with split and decontamination, paired scorecard, local JSON registry, promote and rollback | Postgres and object store, web dashboard, REST control plane, RBAC, notifications, synthetic generator | the original defers all of these past the PoC (PRD §9.2, **Verified**) |
| CLI: `demo`, `doctor`, `status`, `suggest`, `build-dataset`, `calibrate`, `fit`, `eval`, `promote`, `rollback`, `trace` | `init`, `watch`, `playground` | the loop needs the first set; the second is convenience |
| Example capabilities: `support.triage` (decision) and one generative sibling | A second host domain | one domain keeps the example rule |
| JSONL and SQLite sinks, dict-of-types validator | JSON Schema and Pydantic validators | flat schemas suffice for the examples; nested ones are the first 1.1 ask |
| Host integration guide, CLI reference, PyPI publish | Hosted anything | package, not a service (original §2.17, **Verified**) |

## 4. Milestones

Each milestone is a release on the roadmap, ends with its tests green, and moves its
rows to Done. Sizes assume one developer; weeks are estimates, not promises.

| # | Release | Theme | Features | Exit gate (a test) | Size |
|---|---|---|---|---|---|
| M1 | 0.3.0 | Capture and both kinds | PX-100 observe-mode capture · PX-101 background sink · PX-070 generative kind through the router · PX-080 scalar calibrator · PX-104 generative example capability · PX-024 OpenAI-compatible local adapter (student and teacher) · PX-028 extras | replay-equivalence; ≤ 5 ms; capture never raises; fault injection passes for the generative kind exactly as for the decision kind; the demo runs both kinds under a second | ~2 weeks |
| M2 | 0.4.0 | Trust the data, trust the eval | PX-040 gate for decision traces · PX-041 dataset builder · PX-030 to PX-034 scorecard and `praxis eval` | decontamination report clean and tested; two builds identical; two evals identical; teacher-vs-teacher shows no delta | ~2 weeks |
| M3 | 0.5.0 | Registry, promotion, status | PX-044 registry, promote, rollback · PX-110 `praxis status` · PX-026 doctor · PX-027 conformance · PX-045 remaining CLI | promotion refused with the failing gate named; rollback is one flag; `status` verdict matches the gates on fixtures; conformance green on every installed adapter | ~1.5 weeks |
| M4 | 0.6.0 | Students and training rungs | PX-020 laya-mlx · PX-042 temperature refit trainer · PX-111 exemplar trainer · PX-112 `praxis suggest` · PX-046 outcome and feedback labels | on the demo, a fitted student's scorecard improves across two dataset versions; `suggest` entries are each verified against a README with a date | ~2 weeks |
| M5 | 1.0.0 | Release | PX-120 host integration guide · PX-121 CLI reference and README · PX-122 one-command definition-of-done test · PX-090 publish | the §2 table, every row a passing test; `pip install` from PyPI runs the demo | ~1 week |

About nine weeks of one developer's time, with the usual caveat that the provider APIs
are weeks old and may move under PX-020.

## 5. Shape of the new pieces (so the milestones are concrete)

- **Observe mode (PX-100).** The router gains `observe(request, answer, info, latency_ms,
  cost_usd)`: the app supplies the main model's answer; Praxis runs the student in
  shadow, validates, records the trace with the app's answer as System-2, never raises.
  For the generative kind the answer is the output object. The Praxis-makes-the-call
  path is unchanged. This is the original S1/S2 "capture is the wedge" (§01 A.8).
- **Background sink (PX-101).** A queue and one daemon thread in front of any sink;
  `record` returns in microseconds; the queue is bounded and drops are counted, never
  raised; `flush()` for tests and shutdown.
- **Generative kind (PX-070).** `GenerativeModel.generate(state, instructions, schema)`
  returns an output and a scalar confidence. Validity through the `SchemaValidator`
  port is the hard gate; the scalar goes through a Platt calibrator (PX-080) fitted on
  (confidence, matched the label) pairs; the same stages, abstain, trace and stats.
  Matching the label is exact after normalisation by default, with a host-supplied
  match function allowed.
- **Local small-LLM adapter (PX-024).** One class over the OpenAI-compatible wire
  protocol (verified on Ollama today), usable as a generative student, as a System-1 for
  decision capabilities (strict JSON schema, self-reported probabilities, calibrated by
  Praxis), and as a teacher. No log-probabilities in 1.0.
- **Exemplar trainer (PX-111).** Rung 0 of the original ladder (§06 §6.1): "fit" indexes
  the captured examples; at serve time the k most similar captured (input → output)
  pairs are the demonstrations in the small LLM's prompt. A real student that learns from
  recorded data, with no gradients, honest about what it is.
- **`praxis status` (PX-110).** From the sink and the registry: the funnel (captured →
  gated → labelled), shadow agreement, calibration error, confident-wrong rate, the
  offload share at the current threshold, latency p50 and p95 for student and teacher,
  a throughput floor (one worker at p50), and a verdict against §2 with the missing
  items spelled out.
- **`praxis suggest` (PX-112).** A JSON catalogue inside the package: per capability
  shape, the student types that fit, the runtime, size, licence, the Praxis rungs that
  apply, and a `verified_on` date. Metadata only, no weights. Bring-your-own-model is
  the same flag with a different name.

## 6. Packaging and the name

**Verified** (`pip index versions` and the downloaded wheel's metadata, 2026-09-30):
`praxis` on PyPI is taken by Google's PAX team ("layers for building neural networks in
Jax", 1.4.0, Apache-2.0, `github.com/google/praxis`), and it **installs an import
package named `praxis`**. `praxis-ai` is taken too. `praxis-core` and `praxis-learning`,
the original design's own names, are free.

So the clash is on the import name, not only the distribution name: a machine with
Google's package installed cannot also import ours as `praxis`. That is a real risk for
an ML-adjacent library whose users may well have JAX tooling installed.

**Question 1 — the name.** Options:
- distribution `praxis-core`, import `praxis` (keeps every example in this repository;
  collides with Google's package when both are installed);
- distribution `praxis-core`, import `praxis_core` (no collision; every import in the
  code and docs changes once, before 1.0, which is cheap now and expensive later);
- a new name for both.

Recommendation: `praxis-core` / `praxis_core`, decided before M1 so the rename lands in
one commit while the public surface is small. The CLI command can stay `praxis`.

Extras at 1.0: `laya-mlx`, `dev`. The small-LLM adapter needs no extra (standard
library HTTP). Python floor 3.11.

## 7. Risks to v1.0 and the test that catches each

| Risk | Caught by |
|---|---|
| A small LLM's self-reported probability is useless for routing | ECE gate in `status`; the demo reports it; sampling-based confidence is the roadmap fallback |
| The generative kind's "matched the label" is too strict for free text | exact match after normalisation is the default; the host match function is tested with a lenient example |
| laya-mlx changes its API (two weeks old) | the spike's exact result dict is in PX-020; the conformance suite fails loudly |
| The one-second demo breaks as stages grow | `tests/test_demo.py` keeps the fake path under a second; real-model runs are separate |
| Capture adds latency on the hot path | the ≤ 5 ms test with the background sink |

## 8. Decisions for the owner

1. **The package and import name** (§6).
2. **LoRA in 1.0 or 1.1.** Recommendation: 1.1, for the reasons in §1. Flip it and M4
   grows by about two weeks plus a serving step.
3. **The generative example capability.** `support.extract` (order id, product, issue
   from the same tickets; recommended) or a `rationale` field on `support.triage`.
4. **Confidence for a small LLM without log-probabilities.** Self-report plus schema
   validity, calibrated and measured in shadow (recommended), with N-sample
   self-consistency as the roadmap fallback.

The default is taken on each unless you say otherwise; the roadmap rows start moving
when M1 starts.
