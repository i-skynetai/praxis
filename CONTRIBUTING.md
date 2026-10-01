# Contributing

## Picking a feature

[ROADMAP.md](ROADMAP.md) lists every planned feature with an ID, a status and an owner,
and it is the source of truth for who is working on what. Take a `Ready` row — *good
first issue* ones are small and self-contained — claim it with the *Claim a feature*
issue template, and set the row to `In progress` with your handle and the date. Your
pull request moves it to `In review`; the merge makes it `Done`. The full rules, and the
[design-note template](docs/features/TEMPLATE.md) for large features, are in the
roadmap.

## Running the checks

```bash
python -m unittest discover -s tests -t .     # the suite: standard library only, no install
python -m praxis_core demo                          # the loop end to end, under a second
python -m mypy                                 # --strict on praxis_core (legacy excluded)
```

The first two need nothing installed. `mypy` is the one development dependency
(`pip install -e ".[dev]"` in a virtual environment, Python 3.11 or later; 3.12 is what
the maintainers develop in). CI runs the suite and the demo on 3.11 to 3.14 and mypy on
3.12; a green run here is the run that matters.

## What a change needs

- **A test that fails without it.** A pass needs a positive observation, not the absence
  of an error. Every guarantee in the README names the test that proves it; a new
  guarantee brings its test.
- **A recorded reason for anything the change makes impossible.** A rule without a
  reason gets relaxed by the next person who finds it inconvenient.
- **Standard library only outside `praxis_core/providers/`.** A test enforces it. Providers
  and trainers are pip extras and import their dependency lazily.
- **No provider name outside `praxis_core/providers/`.** A test enforces that too. The core
  promises a contract, not an adapter.
- **`mypy --strict` clean** on the files it already covers.
- **The demo still green.** `python -m praxis_core demo` is the README; it runs in CI.

## Adding an adapter

Implement the port from `praxis_core/ports.py` — a `DecisionModel` has `info` and
`decide(state, questions) -> {name: RawAnswer}`; a `Teacher` has `info` and
`answer(state, questions) -> {name: TeacherAnswer}` — and it routes. Nothing in the core
needs to know what is behind it. Before writing one, re-read the provider's current
README: the System-1 model APIs are weeks old and move. Map the provider's own
confidence into `native_confidence` and leave routing confidence to Praxis; accept
`noul` as the vendor spelling of `boolean`; and let exceptions escape — the router turns
them into abstentions, and hiding them would hide the failure rate.

## What will be refused

- **A System-1 failure that reaches the caller.** An error, a timeout or a malformed
  answer is an abstention with a reason, never an exception. The fault-injection tests
  in `tests/test_router.py` are the contract.
- **A student that reports itself trained when it is not.** `LoraStudent.fit` raises
  until a backend is wired in, and the nearest-neighbour model answers uniform (never
  served) until it is fitted. Confident-wrong is the exact failure this project exists to
  prevent, and a student that pretends to be trained is the purest form of it.
- **Deflection reported on its own.** Any metric change keeps confident-wrong as a
  separate column. A number that can be improved by answering more things wrongly is not
  a measure of quality.
- **A silently skipped trace.** The dataset builder reports every skip by reason. "Probably
  fine" is not one of them.
- **A product, host or vendor in the core or the docs.** The only example capability is
  `support.triage`.

## Style

Match the file you are editing. The code explains its own reasoning in docstrings; keep
that habit — the *why* is the part that survives.
