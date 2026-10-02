# Design decisions

A short log of the decisions this codebase is built on: what was decided, why, and what
it costs. Each one is dated and can be revisited; a new decision gets a new entry rather
than a silent edit. Format: context, decision, consequences.

## D-01 — A library at the model-call seam, not a proxy in front of the app (2026-09)

**Context.** Mirroring an API gateway was the obvious shape. A proxy sees bytes: it cannot
tell a well-formed answer from a plausible one, cannot judge confidence against a declared
type, and adds a network hop. **Decision.** Praxis is imported inside the app, where the
types still exist: a capability declares its questions or its output schema, and every
stage (capture, calibrate, route, record) reads that declaration. **Consequences.** The app
changes one call site per capability; new app endpoints need nothing from Praxis; Praxis
must be safe to run in-process (see D-07).

## D-02 — Ports and adapters; the core is standard library only (2026-09)

**Context.** Providers are weeks old and will move; hosts run different stacks. **Decision.**
Eight small `Protocol`s (`praxis_core/ports.py`) are the whole contract; every provider,
sink, calibrator, trainer and registry is an adapter behind one; `praxis_core` outside
`providers/` imports only the standard library; a vendor name may appear only under
`providers/`. Both rules are tests. **Consequences.** `pip install` pulls nothing; tests
run on fakes; a vendor change is contained in one file.

## D-03 — Capture first, in observe mode (2026-09-30)

**Context.** The original design's wedge is "the app keeps calling its own model and hands
Praxis the answer"; the first implementation only let Praxis make the call. **Decision.**
`observe()` is a first-class entry point on both routers: validate, run the student in
shadow, record, never raise. Praxis-makes-the-call stays as `decide()` / `generate()`.
**Consequences.** Adoption needs no behaviour change on day one; the frontier teacher
adapters are unnecessary to start, and no test may need one.

## D-04 — Two capability kinds, one loop (2026-09-30)

**Context.** The September redesign added decision models (typed answers with
probabilities) as a student class; the owner's framing is "the small model is any model".
**Decision.** `decision` (choice, score, yes-no) and `generative` (an output against a
schema) are two kinds of capability through the same eight router steps, two student
ports, one trace envelope. **Consequences.** Extraction and structured generation are
first-class; the validator is the hard gate for the generative kind; a scalar calibrator
was needed beside the distribution one (D-06).

## D-05 — Confidence is one minus normalised entropy, computed by Praxis (2026-09-30)

**Context.** Every provider reports confidence on its own scale; a threshold would mean
three different things. **Decision.** For a distribution, `1 - H(p)/log(n)` on the
*calibrated* distribution; the provider's own number is kept beside it as
`native_confidence` for audit and never routed on. **Consequences.** One threshold is
comparable across providers and question types; adapters stay thin.

## D-06 — Calibration is a core component, fitted per shape (2026-09-30)

**Context.** A provider shipped with a bucket it labels uncalibrated; a self-reported
confidence can be arbitrary. **Decision.** A temperature per (question type, option count)
for distributions and a Platt map for scalars, both fitted on traces that carry both
answers, both standard library; an unfitted group passes through unchanged and the result
says `calibrated = False`. **Consequences.** Calibration state is visible on every trace and
result; D-09 can be enforced.

## D-07 — The student can never fail the call; the teacher is the only thing that can (2026-09-30)

**Context.** The safety contract from the original design: no path where a student failure
is user-visible. **Decision.** A System-1 error, timeout, malformed answer, or misbehaving
calibrator is an abstention with a reason; the trace path swallows and counts sink
failures; a teacher failure is recorded, then raised as `TeacherError`, because there is
nothing behind the teacher and inventing an answer would be worse. **Consequences.** The
fault-injection suite is the contract every adapter is held to.

## D-08 — Routing is per question (2026-09-30)

**Context.** A decision request carries several questions; the plan routed the call as a
unit. **Decision.** Each question is served or abstained on its own; the teacher is asked
only the abstaining ones. **Consequences.** Cheaper teacher calls; a request can be partly
System-1 and partly System-2; the trace records both per question.

## D-09 — Nothing is served without a fitted calibrator when the policy says so (2026-10-01)

**Context.** The demo served 63 wrong extractions out of 66 because a baseline that
cannot extract reported similarity as confidence and the calibrator had nothing to fit.
**Decision.** `RoutingPolicy.require_calibrated`: a confidence that did not pass a fitted
calibrator is an abstention (`uncalibrated`), and a readiness verdict after shadow names
what is missing. **Consequences.** Shadow precedes serving by construction; the demo's
generative stage honestly serves nothing until a better student exists.

## D-10 — The yes/no type is `boolean`; `noul` is accepted on input (2026-09-30)

**Context.** Two providers call the type `noul`. **Decision.** The vendor-neutral name is
`boolean`; `noul` is accepted by `Question` and never written. `rank` is derived from
`choice` and never reaches an adapter. **Consequences.** Adapters map names at the edge;
the contract reads plainly.

## D-11 — Distribution `praxis-core`, import `praxis_core`, command `praxis` (2026-09-30)

**Context.** `praxis` on PyPI is another project that also installs an import package
named `praxis`. **Decision.** Rename before anything is published, while the surface is
small. **Consequences.** A one-time rename; the legacy modules moved under
`praxis_core.legacy` until their replacements land.

## D-13 — Safe by default, and promotion is a gate, not advice (2026-10-01)

**Context.** The first outside review built a router with no policy and a student that
was always sure, and was served an uncalibrated answer; the demo printed "stays in
shadow" and then ran canary and serve anyway. Both contradicted the README.
**Decision.** `RoutingPolicy` defaults to `stage="shadow"` and `require_calibrated=True`;
`router.readiness()` is the verdict, computed from the router's own shadow comparisons
against thresholds on the policy; `set_stage` past shadow raises `NotReady` until it is
ready, and `force=True` is counted. **Consequences.** The README's claims are the
defaults; the opt-out is a visible policy field the tests use by name; the demo stops at
the gate for the capability that is not ready and says so.

## D-12 — Trust the loop before the model: no fine-tuning in v1.0 (2026-09-30)

**Context.** The original design's ordering rule, and the v1.0 scope. **Decision.** v1.0
ships gradient-free students (a decision model plus a fitted temperature, retrieved
demonstrations for a small LLM, baselines) and the full loop around them; LoRA is the
first feature after 1.0 behind the same `Trainer` port. **Consequences.** Everything in
v1.0 runs on a laptop with no GPU and no key; the trainer port is proven before the
expensive rung lands.
