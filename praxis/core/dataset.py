"""From traces to decision examples: the smallest useful dataset builder.

A System-2 answer recorded on a trace is a candidate label. This module turns those into
``DecisionExample`` rows, one per question, and refuses a trace whose question definition
no longer matches the capability's current one: a silently edited option list must not
poison a dataset (plan §3.5). Group-aware splitting, decontamination and the manifest are
Phase 4; this is what the baseline student and the calibrator need today.
"""
from __future__ import annotations

from typing import Iterable

from .contracts import Capability, DecisionExample, Question, TraceEvent


def label_key(example: DecisionExample) -> str:
    """The distribution key an example's label corresponds to."""
    question = question_of(example)
    return question.as_choice().key_for(example.label)


def question_of(example: DecisionExample) -> Question:
    """Rebuild the question an example was presented with (instructions are not needed
    for keys, so a placeholder stands in)."""
    payload = example.options_or_levels
    if example.question_type in ("choice", "rank"):
        return Question(example.question_type, "-", dict(payload.get("options") or {}))
    if example.question_type == "score":
        return Question("score", "-", levels=tuple(payload.get("levels") or ()))
    return Question("boolean", "-")


def options_or_levels(question: Question) -> dict[str, object]:
    if question.type in ("choice", "rank"):
        return {"options": dict(question.options)}
    if question.type == "score":
        return {"levels": list(question.levels)}
    return {}


def examples_from_traces(traces: Iterable[TraceEvent], capability: Capability | None = None,
                         dataset_version: str | None = None) -> tuple[list[DecisionExample], dict[str, int]]:
    """Labelled examples from traces that carry a System-2 answer.

    Returns the examples and a report: how many traces were read, how many questions
    became examples, and how many were skipped and why. Nothing is skipped silently.
    """
    report = {"traces": 0, "examples": 0, "skipped_not_label_candidate": 0, "skipped_no_system2_answer": 0,
              "skipped_hash_mismatch": 0, "skipped_other_capability": 0, "skipped_not_distillable": 0}
    examples: list[DecisionExample] = []
    for trace in traces:
        report["traces"] += 1
        if capability is not None and trace.capability != capability.name:
            report["skipped_other_capability"] += 1
            continue
        if not trace.label_candidate:
            report["skipped_not_label_candidate"] += 1
            continue
        if not trace.teacher_distillable:
            report["skipped_not_distillable"] += 1
            continue
        for q in trace.questions:
            if q.system2_answer is None:
                report["skipped_no_system2_answer"] += 1
                continue
            if capability is not None:
                declared = capability.questions.get(q.name)
                if declared is None or declared.definition_hash != q.options_or_levels_hash:
                    report["skipped_hash_mismatch"] += 1
                    continue
            examples.append(DecisionExample(
                trace.capability, q.name, q.question_type, trace.state, options_or_levels(q.question),
                q.system2_answer, "system2", q.system2_distribution,
                {"trace_id": trace.trace_id, "host_partition": trace.host_partition, "source": trace.source,
                 "dataset_version": dataset_version, "question_hash": q.options_or_levels_hash}))
            report["examples"] += 1
    return examples, report
