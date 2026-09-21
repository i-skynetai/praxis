"""The eval table. A student is worth deploying only against a number.

Held-out traces, teacher output as ground truth, and three figures that matter:
how often the student is *right*, how often it is *confidently wrong*, and how much
traffic it takes off the teacher.

Confident-wrong is the one to watch. A student that defers is merely useless; a student
that answers wrongly with high confidence is worse than no student at all, and the
deflection rate on its own hides it.
"""
from __future__ import annotations
from typing import Any


def split(traces: list, holdout: float = 0.25) -> tuple[list, list]:
    accepted = [t for t in traces if t.accepted]
    cut = max(1, int(len(accepted) * (1 - holdout)))
    return accepted[:cut], accepted[cut:]


def evaluate(student: Any, held_out: list, threshold: float = 0.7) -> dict:
    answered = correct = confident_wrong = deferred = 0
    for t in held_out:
        out, conf = student.predict(t.inputs)
        if conf < threshold:
            deferred += 1
            continue
        answered += 1
        if out == t.output:
            correct += 1
        else:
            confident_wrong += 1
    n = len(held_out) or 1
    return {"held_out": len(held_out), "answered": answered, "deferred": deferred,
            "correct": correct, "confident_wrong": confident_wrong,
            "accuracy_when_answering": round(correct / answered, 3) if answered else None,
            "deflection": round(answered / n, 3),
            "confident_wrong_rate": round(confident_wrong / n, 3)}


def table(rows: dict[str, dict]) -> str:
    """One row per student or threshold. This is what goes in the pull request."""
    head = f"{'student':22s} {'deflect':>8s} {'accuracy':>9s} {'conf-wrong':>11s} {'deferred':>9s}"
    lines = [head, "-" * len(head)]
    for name, r in rows.items():
        acc = "—" if r["accuracy_when_answering"] is None else f"{r['accuracy_when_answering']:.3f}"
        lines.append(f"{name:22s} {r['deflection']:>8.3f} {acc:>9s} "
                     f"{r['confident_wrong_rate']:>11.3f} {r['deferred']:>9d}")
    return "\n".join(lines)
