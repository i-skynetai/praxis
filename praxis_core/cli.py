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
    from praxis_core.demo import Providers, run_demo

    providers = Providers()
    if args.provider:
        from praxis_core.providers import chat_completions_adapter
        adapter = chat_completions_adapter(args.provider, args.model, args.api_key, timeout_s=args.timeout)
        roles = {r.strip() for r in args.roles.split(",") if r.strip()}
        unknown = roles - {"teacher", "system1", "student"}
        if unknown:
            raise SystemExit(f"--roles: unknown role(s) {sorted(unknown)}; choose from teacher, system1, student")
        providers = Providers(teacher=adapter if "teacher" in roles else None,
                              system1=adapter if "system1" in roles else None,
                              student=adapter if "student" in roles else None)

    sink: TraceSink | None = None
    if args.jsonl:
        from praxis_core.trace import JsonlTraceSink
        sink = JsonlTraceSink(args.jsonl)
    elif args.sqlite:
        from praxis_core.trace import SqliteTraceSink
        sink = SqliteTraceSink(args.sqlite)
    summary = run_demo(tickets=args.tickets, threshold=args.threshold, seed=args.seed, sink=sink,
                       out=None if args.json else print, providers=providers)
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
    demo.add_argument("--provider", metavar="BASE_URL",
                      help="a chat-completions server (a local model server or a proxy) to stand in for the fakes, e.g. http://localhost:11434/v1")
    demo.add_argument("--model", default="granite4.1:3b", help="the model name on that server")
    demo.add_argument("--api-key", default="none", help="bearer token for that server (local servers ignore it)")
    demo.add_argument("--roles", default="teacher",
                      help="which roles the server plays, comma-separated: teacher, system1, student (default teacher)")
    demo.add_argument("--timeout", type=float, default=120.0, help="seconds per call to that server")
    demo.set_defaults(func=_demo)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result: int = args.func(args)
    return result


if __name__ == "__main__":
    sys.exit(main())
