# PX-071 — LoRA trainer for generative students

**Status:** Ready, after 1.0 · **Owner:** unclaimed · **Issue:** none yet

## What is missing today

A generative capability (`support.extract` in the demo) can be captured, labelled and
routed, but the only student is the nearest-neighbour baseline, which copies the output
of the most similar ticket it has seen. It cannot extract, so its verdict stays
"stays in shadow" and nothing is served. That is the correct outcome for a baseline, and
the reason this feature exists: run `python3 -m praxis_core demo` and read the
`support.extract` block.

## What done looks like

Each line is a test that fails today and passes after:

- A trainer behind the `Trainer` port turns the generative examples from
  `generative_examples_from_traces` into a LoRA adapter on a small base model, and
  returns a `ModelArtifact` naming the base, the adapter and the data it saw.
- With no training backend installed, the trainer raises. It never returns a student
  that reports itself trained when it is not.
- The trained adapter is served through the chat-completions plug-in as a
  `GenerativeModel`, and a Platt calibrator is fitted on its shadow traces.
- On the demo's `support.extract` traffic, the trained student reaches a ready verdict
  where the baseline does not, with confident-wrong reported beside the share served.

## Design

1. **Get the baseline number first.** The nearest-neighbour student on the same split is
   the number to beat. Without it, "it seems better" is how a worse model ships.
2. **Collect enough accepted examples.** The dataset report counts every skip by reason.
   Fix the reasons before collecting more: a schema mismatch that rejects a third of the
   traces is a bug in the capability, not a data-volume problem.
3. **Train.** `mlx-lm` on Apple Silicon first, `peft` elsewhere, each a pip extra imported
   lazily, never a core dependency. The `Trainer` port takes decision examples today; it
   needs a generative variant, which is a port change to agree on the issue first.
4. **Calibrate before serving.** A fine-tuned model's own probability is not a
   confidence. The Platt calibrator is fitted on shadow traces, and the readiness gate
   refuses canary until it is.
5. **Pick the threshold from the numbers, not by feel.** The highest share served whose
   confident-wrong rate is acceptable is a product decision; the scorecard (PX-030 to
   PX-034) makes it a visible one.

## What it does not do

No hosted training, no GPU in CI, no change to the decision path. Decision students
keep their own ladder (temperature refit, a closed-form head, then fine-tuning).

## How it is measured

`support.extract` on the demo's synthetic tickets, a held-out split from the dataset
builder: agreement with the teacher, calibration error before and after the Platt fit,
share served by System-1, and confident-wrong. Before: the baseline's numbers from the
demo. After: the trained student's, on the same split.
