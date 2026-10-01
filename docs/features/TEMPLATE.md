# PX-XXX — Feature name

<!-- Copy this file to docs/features/PX-XXX-short-name.md for an L-sized feature, fill it
in, and link it from the feature's issue. Agree it there before writing the code. -->

**Status:** Proposed · **Owner:** @handle · **Issue:** #

## What is missing today

What a host or an agent cannot do, or gets wrong, and how you know — a command and its
output, a file and line, a measurement.

## What done looks like

Each line is a test that fails today and passes after:

- …

## Design

The smallest change that meets the list above. Name the files it touches. If it needs a
new port, a new field on the contract or a new envelope version, say why the existing
ones do not fit — that is a decision to make on the issue before the code. Provider
names stay under `praxis_core/providers/`; the core stays standard library only.

## What it does not do

The boundary, so review can hold it.

## How it is measured

The capability and traffic used (the demo's `support.triage` unless there is a reason
not to), the numbers before, and the numbers after: accuracy against System-2 labels,
calibration error, share served by System-1, confident-wrong.
