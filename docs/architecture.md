# Architecture

Five stages. Each one owns a single decision.

```
  1 seam       what is this capability, and what shape is a valid answer?
  2 capture    what did the teacher actually do?
  3 gate       is this trace good enough to learn from?
  4 student    can I answer this, and how sure am I?
  5 router     who answers this request?
       │
  6 evaluate   is the student worth deploying?
```

## 1 · Seam

A `Capability` is a name, an instruction and an output schema. The schema is the
contract — every stage downstream reads it.

Because the seam is inside the application, the types are still present. A gateway sees
a JSON body; the seam sees a declared shape and can say *why* an answer is wrong.

## 2 · Capture

`call_teacher` runs the expensive model and returns a `Trace`: the inputs, the output,
the model, latency and cost. Its `key` is a hash of capability plus inputs, which is
how duplicates are detected later.

## 3 · Gate

Four checks, cheapest first: right capability, valid schema, within the latency bound,
not already seen.

Rejections are counted **by reason**. A flywheel that quietly drops 40% of its traces on
a schema mismatch looks identical to one that is working, right up until the student is
bad and nobody knows why.

## 4 · Student

`fit(traces)` and `predict(inputs) -> (output, confidence)`. That is the whole contract,
which is why swapping a nearest-neighbour baseline for a LoRA model changes nothing else.

Only accepted traces reach `fit`. The gate is not advisory.

## 5 · Router

Three outcomes:

| Condition | Answered by |
|---|---|
| no student | teacher |
| confidence below threshold | teacher |
| confident but output fails the schema | teacher |
| confident and valid | student |

The third row is the interesting one. A student that is sure and wrong-shaped is more
dangerous than one that is unsure, so the router validates before trusting.

Every decision goes in the ledger. "The student handles 60% of traffic" has to be
checkable.

## 6 · Evaluate

Held-out traces, teacher output as ground truth. Three numbers: deflection, accuracy
when answering, and **confident-wrong rate**.

Ship on the third one.
