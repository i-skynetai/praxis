# Contributing

## Running the tests

```bash
python3 -m unittest discover -s tests -t .
```

20 cases, standard library only — no install step, nothing to pin. That is the same
command CI runs, so a green run here is the run that matters.

## What a change needs

- **A test that fails without it.** A pass needs a positive observation, not the absence
  of an error.
- **A recorded reason for anything the change makes impossible.** A rule without a
  reason gets relaxed by the next person who finds it inconvenient.
- **No new dependency in the core.** A real student will need a training stack; that
  belongs behind the `fit`/`predict` interface, not in the seam, the gate or the router.

## Adding a student

Implement `fit` and `predict(inputs) -> (output, confidence)` and it routes. Nothing
else in the project needs to know what is behind it — see
[docs/distillation.md](docs/distillation.md).

## What will be refused

- **A student that reports itself trained when it is not.** `LoraStudent.fit` raises
  until a backend is wired in, and it should keep raising rather than fall back quietly.
  Confident-wrong is the exact failure this project exists to prevent, and a student
  that pretends to be trained is the purest form of it.
- **Deflection reported on its own.** Any metric change keeps confident-wrong as a
  separate column. A number that can be improved by answering more things wrongly is not
  a measure of quality.
- **A gate that accepts a trace it cannot check.** Four checks, each with a reason for
  rejection. "Probably fine" is not one of them.
- **Moving the seam out of the application.** A proxy sees bytes; the seam sees a
  declared shape. That difference is the whole design.

## Style

Match the file you are editing. The code explains its own reasoning in docstrings; keep
that habit — the *why* is the part that survives.
