"""The command line. ``praxis demo`` today; ``init``, ``doctor``, ``trace``, ``build-dataset``,
``calibrate``, ``train``, ``eval`` and ``promote`` arrive with their phases (plan §3.8)."""
from __future__ import annotations

import argparse
import json
import sys
from typing import Sequence

from praxis_core import __version__


def _demo(args: argparse.Namespace) -> int:
    from praxis_core.ports import TraceSink
    from praxis_core.demo import run_demo

    sink: TraceSink | None = None
    if args.jsonl:
        from praxis_core.trace import JsonlTraceSink
        sink = JsonlTraceSink(args.jsonl)
    elif args.sqlite:
        from praxis_core.trace import SqliteTraceSink
        sink = SqliteTraceSink(args.sqlite)
    summary = run_demo(tickets=args.tickets, threshold=args.threshold, seed=args.seed, sink=sink,
                       out=None if args.json else print)
    if args.json:
        print(json.dumps(summary.as_dict(), indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="praxis", description="A System-1 / System-2 decision and training framework.")
    parser.add_argument("--version", action="version", version=f"praxis {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    demo = sub.add_parser("demo", help="run support.triage end to end with the fake teacher and the baseline student")
    demo.add_argument("--tickets", type=int, default=60, help="tickets per stage (default 60)")
    demo.add_argument("--threshold", type=float, default=0.5, help="serve when Praxis confidence is at least this")
    demo.add_argument("--seed", type=int, default=7)
    demo.add_argument("--jsonl", metavar="PATH", help="also write every trace to this JSONL file")
    demo.add_argument("--sqlite", metavar="PATH", help="also write every trace to this SQLite file")
    demo.add_argument("--json", action="store_true", help="print the summary as JSON instead of the table")
    demo.set_defaults(func=_demo)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result: int = args.func(args)
    return result


if __name__ == "__main__":
    sys.exit(main())
