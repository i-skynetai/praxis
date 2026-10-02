# Changelog

All notable changes, newest first. Versions follow semantic versioning; nothing is
published to PyPI yet.

## 0.3.2 — 2026-10-01 — safe by default, and the first public release

Found by the first outside review of the committed tree. Behaviour changes are marked.

- **Changed: safe defaults** (PX-900, the one P0). `RoutingPolicy()` is now
  `stage="shadow"`, `require_calibrated=True`. A router built with no policy serves
  nothing from the student until a calibrator is fitted and the stage is raised. Code
  that relied on the old defaults must say `stage="serve", require_calibrated=False`.
- **Changed: the readiness gate** (PX-901). `router.readiness()` returns the verdict
  (comparisons, agreement, calibrator, what is missing) against thresholds on the policy.
  `set_stage("canary" | "serve")` raises `NotReady` until it is ready; `force=True`
  overrides and is counted. `NotReady`, `Readiness` and `GenerativeRouter` are exported.
  The demo stops `support.extract` at the gate instead of running canary anyway.
- **Removed: `praxis_core.legacy`** (PX-902), the v0.1 modules PX-070 replaced, with
  their 20 tests. The LoRA note is now the PX-071 design note.
- **Docs match the code** (PX-902): a test runs the README's steps verbatim; the demo
  picture is rendered from a real run by a script beside it; `python3` in the quick
  start; CONTRIBUTING, architecture and three pictures corrected.
- **Fixed:** the HTTP plug-in closes error responses (PX-903); no more
  `ResourceWarning` on Python 3.14.
- 154 tests on Python 3.11 to 3.14; ruff and `mypy --strict` clean.

## 0.3.1 — 2026-10-01 — the showcase bar

- A **decision log** (`docs/decisions.md`): twelve dated entries, each with context,
  decision and consequences.
- **ruff** (lint and format) configured and enforced in CI beside mypy; the code is
  formatted and lint-clean. A **Makefile**: `make check` is what CI runs.
- README front page shortened to a two-minute read; the ports table and the training
  ladder moved to the architecture doc; CONTRIBUTING points at `make check`.
- The release plan gains "the showcase bar", a definition of done for every release:
  runs in sixty seconds from a clone, one command checks everything, plain words,
  every guarantee a test, every decision logged, every planned feature a claimable row.

## 0.3.0 — 2026-10-01 — capture, and both capability kinds (milestone M1 of v1.0)

- **Renamed**: distribution `praxis-core`, import `praxis_core`, command `praxis`. The
  PyPI name `praxis` belongs to another project that also imports as `praxis`. The
  original v0.1 modules live in `praxis_core.legacy` until their replacements land.
- **Observe mode** (PX-100): the app keeps calling its own model and hands Praxis the
  answer; Praxis validates it, runs the student in shadow, records the trace, and never
  raises. `TraceEvent.to_request()` rebuilds the request a trace recorded.
- **Background sink** (PX-101): `QueuedTraceSink` makes capture cost microseconds; a
  full queue drops and counts, a dead sink is counted, nothing blocks or raises.
- **Generative capabilities** (PX-070): `GenerativeRouter` runs the same eight steps for
  outputs against a schema, with the validator as the hard gate, a scalar calibrator on
  the student's confidence, and a host-supplied match function.
- **Platt calibrator** (PX-080) behind a new `ScalarCalibrator` port.
- **`require_calibrated`** on `RoutingPolicy`: serve nothing whose confidence did not
  pass a fitted calibrator. Added after the demo served 63 wrong extractions out of 66.
- **`support.extract`** (PX-104): the generative example beside `support.triage`; the
  demo runs both kinds, with a readiness verdict after shadow, in about 120 ms.
- **Chat-completions adapter** (PX-024): one standard-library adapter in three roles
  (generative student, System-1, teacher) for any local model server or proxy speaking
  that protocol; verified live against a local server.
- **Extras rule** (PX-028): adapters import their dependency lazily and a missing one
  names the extra to install.
- 163 tests on Python 3.11 to 3.14; `mypy --strict` clean.

## 0.2.0 — 2026-09-30 — the redesign lands (Phases 0 and 1)

- Contracts (typed questions, request, result, trace envelope v2), seven ports with
  one fake each, the decision router with abstain, shadow and canary, the temperature
  calibrator, JSONL and SQLite sinks, the nearest-neighbour baseline, and
  `python -m praxis demo`.
