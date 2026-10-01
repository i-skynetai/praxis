# Changelog

All notable changes, newest first. Versions follow semantic versioning; nothing is
published to PyPI yet.

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
