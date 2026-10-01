# One command per check. `make check` is what CI runs.
PY ?= python3

.PHONY: check test lint format typecheck demo

check: lint typecheck test

test:
	$(PY) -m unittest discover -s tests -t .

lint:
	$(PY) -m ruff check praxis_core tests
	$(PY) -m ruff format --check praxis_core tests

format:
	$(PY) -m ruff format praxis_core tests
	$(PY) -m ruff check --fix praxis_core tests

typecheck:
	$(PY) -m mypy

demo:
	$(PY) -m praxis_core demo
