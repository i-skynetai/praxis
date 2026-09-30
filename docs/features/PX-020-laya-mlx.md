# PX-020 — Apple-Silicon decision-model adapter (`laya-mlx`)

**Status:** Proposed · **Owner:** — · **Issue:** —

The first real System-1. Every statement below is labelled **Verified** (where), **To
verify** (before or during the build), or **Question** (a decision, not a fact). Sources
were re-read on 2026-09-30, the day this note was written; the provider is two weeks old
and will move.

## What is missing today

`python -m praxis demo` closes the loop on the nearest-neighbour baseline only. No
adapter exists for a real decision model, so Praxis has never routed a call through
the class of model the redesign is about, and the demo's shadow-warm agreement (0.73 on
the rule teacher, **Verified** `python -m praxis demo`) has no real number to beat.

## What the provider is (Verified, 2026-09-30)

| Fact | Value | Where |
|---|---|---|
| Package | `laya-mlx` 0.2.0, released 2026-09-22 (0.1.0 on 2026-09-19) | PyPI page; `pip index versions laya-mlx` |
| Requires | Python ≥ 3.11; `mlx>=0.32.2,<0.33` (marker: darwin + arm64), `huggingface-hub>=0.34,<2`, `numpy>=1.26`, `tokenizers>=0.21,<1`; macOS 14+ | wheel `METADATA` read from the downloaded wheel; README "Apple Silicon, Python 3.11+, macOS 14+" |
| Installs here | yes: mlx 0.32.3 + mlx-metal on this M4 Pro, macOS 26.3, Python 3.12.13 | `pip install laya-mlx` in a scratch venv this session |
| Load | `agent = laya_mlx.load("aac6fef/laya-mlx", dtype="float16")`; parameters `dtype`, `batch_size`, `device`, `compile`, `pad_to_multiple`, `cache_prompts`, `subfolder`, `revision` | README "Python API" |
| Checkpoints | `aac6fef/laya-mlx` (English, 421M), `aac6fef/laya-multilingual-mlx` (322M), `aac6fef/laya-typed-decisions-mlx` (421M, fine-tuned, 1,024 context) | README "Supported checkpoints" |
| Predict | `agent.predict(state, questions)`; state may be text, a JSON dict or a conversation list; questions are `{name: {"type", "instructions", "criteria"}}` | README code blocks 1–2 |
| Types | `choice` (criteria: dict key→description or list of labels), `score` (criteria: ordered level descriptions), `noul` (yes/no, no criteria) | README code block 2 |
| Result | `result["answers"][name]`; results "retain upstream's four-decimal rounding, `action.act_probability`, and token usage fields" | README "Python API" |
| Upstream result fields | choice: `choice`, `probabilities` (dict by key), `confidence` (1 − normalised entropy), `answer_confidence`; score: `score` (expected level), `probabilities` (list), `confidence`; noul: `noul` (P(true)), `probabilities` `{"false", "true"}`, `confidence` | upstream `NandhaKishorM/laya` README, result example |
| Calibration | checkpoint temperatures per (question type, option count) are applied at load and clamped to [0.5, 5.0]; raw values on `agent.temperature_raw` / `agent.temperature_by_options_raw` | README; upstream README |
| Option limits | "choice token budget shared across options; use `predict_shortlist()` for 100+ labels"; upstream: HTTP cap 100 options, practical cap about 20 before truncation; score levels need descriptions | README "Shortlisting"; upstream "Limits" |
| Speed | 13.42 ms median for one short English question on an M3 Max, FP16; 7.39 ms multilingual; 943.6 MiB peak | README "Performance on M3 Max" |
| Training | "inference and conversion; RLCD training and fine-tuning remain in the upstream project" | README |
| Licence | Apache-2.0; models by Convai Innovations | README "Attribution and license" |

**Verified by a spike on this machine (M4 Pro, 48 GB, macOS 26.3, Python 3.12.13,
laya-mlx 0.2.0, mlx 0.32.3; 2026-09-30).** Both checkpoints were loaded with
`laya_mlx.load(repo, dtype="float16")` and asked the three `support.triage` questions
about one ticket ("charged twice on the invoice ... we need this today ... we might
switch providers"; the rule teacher says billing / 2 / true).

| | `laya-typed-decisions-mlx` | `laya-mlx` (base) |
|---|---|---|
| load, download included | 39.4 s | 30.3 s |
| first predict (warm-up) | 1,457 ms | 330 ms |
| warm predict, 3 questions, 277 input tokens, median of 10 | **40.9 ms** | 41.6 ms |
| department | billing 0.772 (confidence 0.433) | billing 0.944 (0.801) |
| urgency | argmax 2, p 0.374, expected 1.90 (0.152) | argmax **1**, p 0.852, expected 1.13 (0.607) |
| churn_risk | P(true) 0.537 → true (0.537) | P(true) 0.366 → **false** (0.634) |
| predict from a worker thread | ok | ok |

One ticket is an anecdote, not a measurement; the demo run below is the measurement.
But it shows the shape of the risk: the base checkpoint was more confident and wrong on
two of three, the fine-tuned one less confident and right on three of three.

The result shape, exactly as returned (this is what the adapter parses; it differs from
the upstream Laya README in three places):

```
{"model": "laya-rl-agent",
 "answers": {
   "department": {"type": "choice", "confidence": 0.4332, "action": {"act_probability": 1.0},
                  "choice": "billing", "probabilities": {"billing": 0.772, "technical": 0.0668,
                                                          "account": 0.0728, "sales": 0.0884}},
   "urgency":    {"type": "score", "confidence": 0.1519, "action": {"act_probability": 1.0},
                  "score": 1.8954, "legend": {"0": "...", "1": "...", "2": "...", "3": "..."},
                  "probabilities": {"0": 0.0233, "1": 0.3303, "2": 0.3739, "3": 0.2724}},
   "churn_risk": {"type": "noul", "confidence": 0.5367, "action": {"act_probability": 1.0},
                  "noul": 0.5367}},
 "usage": {"input_tokens": 277, "output_tokens": 0}}
```

- `score.probabilities` is a **dict keyed by the level index as a string** (upstream
  documents a list). Those are Praxis's own score keys.
- `noul` carries **no `probabilities`**; only `noul` = P(true). The adapter builds
  `{"true": noul, "false": 1 - noul}`.
- `confidence` is not one formula: for `choice` it is 1 − normalised entropy (0.433 for
  the distribution above checks out), for `noul` it is P(answer) (0.5367 and, on the base
  checkpoint, 0.6338 = 1 − 0.3662). There is no `answer_confidence`. Praxis keeps the
  number as `native_confidence` for audit and routes on its own.
- Probabilities are rounded to four decimals; the ones above sum to 1.0000, but the
  adapter renormalises anyway.
- Temperatures are per **option-count bucket**, not per exact count:
  `choice:2`, `choice:3-5`, `choice:6-10`, `choice:11+`, `score:3-5`, `noul:2`, applied by
  the library before the probabilities are returned. Both checkpoints ship
  `choice:11+ = 0.1006`, which the library clamps to 0.5 with a `RuntimeWarning` telling
  the caller to treat confidence from that bucket as uncalibrated. Praxis's calibrator
  per (type, exact count) sits on top and fits whatever comes out.
- The first predict after load costs 0.3 to 1.5 s, so the adapter warms up in
  `__init__`; the router's default 2 s timeout would otherwise turn the first routed call
  into an abstention.
- `laya_mlx.__version__` is `"0.2.0"`. Public API also exposes `Router`, `predict_shortlist`,
  `system_one`, `embed_fn_from_agent`, presets.

**Still to verify during the build:** the HF cache size per checkpoint (the download
took about 30 s each on this connection); behaviour with more than 10 options (the
uncalibrated `choice:11+` bucket); whether two concurrent `predict` calls are safe (the
router never issues two at once per instance, so a lock is the conservative default).

## What done looks like

Each line is a test that fails today and passes after:

- `pip install -e ".[laya-mlx]"` installs the extra; `import praxis.providers` pulls no
  `mlx`; importing the adapter without the extra raises an `ImportError` naming it.
- The adapter satisfies `DecisionModel`, maps every Praxis question type to the
  provider's (`boolean` → `noul`, `rank` never arrives), returns a distribution keyed by
  the question's own keys that passes `check_distribution`, and puts the provider's
  `confidence` in `native_confidence`.
- The conformance suite (PX-027) passes on it: same requests as the fakes, same result
  shape, exceptions surface as router abstentions.
- `python -m praxis demo --system1 laya-mlx` runs the four stages on the real model,
  prints the same table, and records `provider = "laya-mlx"` on every trace.
- `praxis doctor` (PX-026) lists it as installed and loadable, and refuses a capability
  with more than 100 options in a choice question before any request.
- Live tests run only when the package imports **and** `PRAXIS_LIVE=1` is set; CI never
  downloads a model.

## Design

`praxis/providers/laya_mlx.py`, one class:

```
LayaMlxDecisionModel(checkpoint="aac6fef/laya-typed-decisions-mlx", dtype="float16",
                     revision=None, warm_up=True, **load_kwargs)
  info      -> ModelInfo("laya-mlx", checkpoint, laya_mlx.__version__, "zero-shot")
  limits    -> AdapterLimits(types={"choice","score","boolean"}, max_options=100, warn_options=20)
  decide(state, questions) -> {name: RawAnswer(distribution, native_confidence=confidence)}
```

- `import laya_mlx` happens inside `__init__`, never at module level (PX-028).
- The model loads eagerly in `__init__` and, with `warm_up`, runs one predict, so the
  first routed call is not the one that pays for the download; the router's 2 s timeout
  would otherwise turn a cold start into an abstention.
- Request mapping: `choice` → `criteria = dict(options)` (descriptions kept, they carry
  meaning to an encoder model); `score` → `criteria = list(levels)`; `boolean` →
  `{"type": "noul", "instructions"}`. The state passes through unchanged.
- Response mapping: choice `probabilities[key]` in declared key order; score
  `probabilities[str(i)]` (already keyed by index); noul `{"true": noul, "false": 1 - noul}`.
  Renormalise to sum to one (four-decimal rounding), then the router validates as for
  any adapter. `native_confidence = answers[name]["confidence"]`, whatever the
  provider's formula for that type.
- Errors are not caught: a missing key, a provider exception or a stall reaches the
  router and becomes an abstention with the reason. Hiding them would hide the failure
  rate.
- A `threading.Lock` around `predict`. The spike proved a worker-thread call works; it
  did not test two in flight, and the router never issues two per instance.
- Praxis's own `TemperatureCalibrator` sits on top of whatever temperature the checkpoint
  applied: composing two temperatures is still a temperature, and the trace records
  both the provider's number and ours.

**Question 1 — default checkpoint.** `aac6fef/laya-typed-decisions-mlx` (fine-tuned;
upstream reports 0.766 accuracy on its typed-decisions benchmark against 0.362 for the
base English checkpoint, **Verified** upstream README; and the one-ticket spike above
points the same way) is the recommendation for the demo. The base checkpoint stays
selectable. The demo run measures both.

**Question 2 — checkpoint pinning.** `load(..., revision=<commit>)` is supported. Pin
the demo's default to a commit for reproducibility, or track `main`? Recommendation:
pin, and bump deliberately.

## What it does not do

No training or fine-tuning (the runtime is inference only). No shortlisting for 100+
options (a later feature, `predict_shortlist`). No batching across requests (the router
is one call at a time). No language routing (`Router` in the library); one checkpoint
per adapter instance.

## How it is measured

`python -m praxis demo --system1 laya-mlx --tickets 60` against the rule teacher:
shadow-warm agreement per question type, share served in the serve stage at the same
threshold, confident-wrong count, and median System-1 latency from the traces, beside
the same numbers for the nearest-neighbour baseline (0.73 agreement, 46 % served, 3
confident-wrong of 83, **Verified** this session). Recorded in this note when measured.
