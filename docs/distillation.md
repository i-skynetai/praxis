# Wiring a generative student

> This page is about the **generative path** (Rung D of the training ladder): a LoRA
> student for a capability that must produce text or code against an output schema. For
> a capability whose answer is a choice, a score or a yes/no, use the decision path in
> [architecture.md](architecture.md): a System-1 decision model behind the
> `DecisionModel` port, calibrated and routed with abstain. That path needs no GPU and
> no training run to get started.

The baseline exists so the flywheel is closed and measurable. This is what replacing it
involves, and the order to do it in.

## 1 · Get a baseline number first

```python
from praxis_core.legacy.evaluate import split, evaluate, table
train, held = split(traces, holdout=0.25)
student = NearestNeighbourStudent(); student.fit(train)
print(table({"nearest-neighbour": evaluate(student, held)}))
```

Without this number, a trained student has nothing to beat, and "it seems better" is
how a worse model ships.

## 2 · Collect enough accepted traces

The gate's `report()` tells you the accepted count and the rejection reasons. Fix the
rejections before scaling collection — a schema mismatch rejecting a third of traces is
a bug in the capability, not a data volume problem.

## 3 · Implement `fit`

`LoraStudent` fixes the interface. A backend needs `transformers` and `peft`, a base
model small enough to serve, and a GPU. The shape:

```python
def fit(self, traces):
    pairs = [(self._prompt(t.inputs), json.dumps(t.output)) for t in traces if t.accepted]
    # tokenise, LoRA-adapt self.base_model at self.rank, train, keep the adapter
    self._fitted = True
```

Keep the refusal in `predict` when `_fitted` is false. It is the property that makes the
rest trustworthy.

## 4 · Calibrate confidence before deploying

A fine-tuned model's raw probability is not a confidence. Calibrate it against held-out
traces — otherwise the router's threshold means nothing and the confident-wrong rate
climbs invisibly.

## 5 · Pick the threshold from the table, not by feel

Run `evaluate` at several thresholds and read the confident-wrong column. The right
threshold is the highest deflection whose confident-wrong rate you can live with, and
that is a product decision, not an engineering one.

## What not to do

**Do not let `fit` fall back.** If training is unavailable the student must raise. A
student that reports itself trained when it is not produces confident wrong answers,
which is the failure this project exists to prevent.

**Do not train on ungated traces.** The gate is the only thing standing between a bad
teacher day and a permanently bad student.

**Do not report deflection on its own.** It is the number that looks best and means
least.
