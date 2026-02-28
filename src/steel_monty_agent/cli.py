from __future__ import annotations

import argparse
import json
import sys

from .config import Settings
from .observability import configure_logfire
from .orchestrator import Orchestrator


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("Value must be >= 1.")
    return parsed


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="steel-monty-agent",
        description="Generate Monty code with an LLM and execute browser actions through Steel.",
    )
    parser.add_argument(
        "objective",
        nargs="+",
        help="Task objective for the browsing agent.",
    )
    parser.add_argument(
        "--session",
        help="Optional fixed session name. Default creates per-attempt names.",
    )
    parser.add_argument(
        "--max-attempts",
        type=_positive_int,
        help="Override max attempts for this run.",
    )
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--local",
        dest="steel_local",
        action="store_const",
        const=True,
        help="Use local Steel mode for this run.",
    )
    mode_group.add_argument(
        "--cloud",
        dest="steel_local",
        action="store_const",
        const=False,
        help="Use Steel cloud mode for this run.",
    )
    parser.set_defaults(steel_local=None)
    parser.add_argument(
        "--api-url",
        help="Explicit Steel API URL for this run.",
    )
    parser.add_argument(
        "--solve-captcha",
        action="store_true",
        help="Enable Steel session auto CAPTCHA solving.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])
    configure_logfire()

    objective = " ".join(args.objective).strip()
    if not objective:
        print("Objective must not be empty.", file=sys.stderr)
        return 2

    try:
        settings = Settings.from_env()
        orchestrator = Orchestrator(settings).with_overrides(
            max_attempts=args.max_attempts,
            steel_local=args.steel_local,
            steel_api_url=args.api_url,
            steel_solve_captcha=True if args.solve_captcha else None,
        )
        result = orchestrator.run(objective=objective, session_name=args.session)
    except Exception as exc:
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

    print(json.dumps(result.to_dict(), indent=2, ensure_ascii=True))
    return 0 if result.success else 1


if __name__ == "__main__":
    raise SystemExit(main())
