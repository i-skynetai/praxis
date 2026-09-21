# Praxis

**Turn expensive frontier calls into a cheap specialised one.** Capture what the big
model does at a typed seam, gate the traces for quality, distil a small student, and
route by confidence with fallback when the student is unsure.

```
  application ──► seam ──► teacher (frontier)
                    │           │
                    │           ▼
                    │        capture ──► gate ──► student
                    │                              │
                    └──────── router ◄─────────────┘
                              student if confident · teacher if not
```

## The decision that shapes it

**Praxis is not an HTTP gateway proxy.** Mirroring a gateway was considered and
rejected. A proxy sees bytes: it cannot tell a well-formed answer from a plausible one,
cannot judge confidence against a declared output type, and forces every application
through a network hop it did not ask for.

The seam sits *inside* the application, where the types still exist. A capability
declares its output schema, and every stage downstream — capture, gate, router, eval —
uses that declaration.

## The parts

| | |
|---|---|
| **seam** | A capability: an instruction and a declared output schema. Calls the teacher, records a trace. |
| **gate** | Four checks — right capability, valid schema, not too slow, not a duplicate. Rejects with a reason. |
| **student** | Anything with `fit` and `predict(inputs) -> (output, confidence)`. |
| **router** | Student above threshold, teacher below. Falls back when the student is confident *and* malformed. |
| **evaluate** | Held-out scoring. Reports confident-wrong separately from deflection. |

## Two students

**`NearestNeighbourStudent`** — the baseline, and honest about being one. Stores accepted
traces, answers by token overlap. No GPU, no training run, no dependency. It exists so
the flywheel is demonstrably closed, and so a LoRA student has a number to beat.

**`LoraStudent`** — the real one. The interface is fixed; `fit` raises until a backend is
wired in. It raises rather than quietly falling back, because a student that reports
itself trained when it is not is precisely the confident-wrong failure this project
exists to prevent.

## Run the flywheel

```python
from praxis.seam import Capability, Trace
from praxis.gate import Gate
from praxis.student import NearestNeighbourStudent
from praxis.router import Router

cap = Capability("classify", "Classify the ticket.", {"label": "str"})
gate = Gate(cap)

traces = [gate.judge(Trace("classify", {"text": t}, {"label": l}, "teacher", 5))
          for t, l in [("login page broken", "bug"), ("add dark mode", "feature"),
                       ("crash on save", "bug"), ("export to csv", "feature")]]

student = NearestNeighbourStudent(); student.fit(traces)
router = Router(cap, student, threshold=0.4)

router.ask({"text": "login broken"},   teacher)   # student, conf 0.75
router.ask({"text": "something else"}, teacher)   # teacher, conf 0.125 below 0.4
router.stats()   # {'asked': 2, 'student': 1, 'deflection': 0.5, ...}
```

## The number that matters

Deflection alone is a vanity metric. `evaluate()` reports **confident-wrong** separately:

```
student                 deflect  accuracy  conf-wrong  deferred
------------------------------------------------------------------
nearest-neighbour         0.500     1.000       0.000         1
```

A student that defers is merely useless. A student that answers wrongly with high
confidence is worse than no student, and deflection hides it.

## Documentation

| | |
|---|---|
| [Architecture](docs/architecture.md) | The five stages, and where each decision is made |
| [Distillation](docs/distillation.md) | Wiring a real student, and what to measure first |

## Status

Python 3.11+, standard library only. **20 tests.** The LoRA backend is not wired in —
see `docs/distillation.md`.

## Licence

Apache 2.0.
