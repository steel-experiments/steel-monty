from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from steel_monty_agent.steel_sdk import SteelSDKBrowser


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="smoke.py",
        description="Smoke test Steel SDK + Playwright CDP integration.",
    )
    parser.add_argument(
        "--url",
        default="https://example.com",
        help="URL to open for smoke testing.",
    )
    parser.add_argument(
        "--session",
        default="steel-monty-smoke",
        help="Steel session namespace/name.",
    )
    parser.add_argument(
        "--local",
        action="store_true",
        help="Use local Steel API/runtime mode.",
    )
    parser.add_argument(
        "--api-url",
        default=None,
        help="Explicit Steel API URL.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=30,
        help="Playwright timeout in seconds.",
    )
    parser.add_argument(
        "--out",
        default="artifacts/smoke",
        help="Output directory for smoke artifacts.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])
    out_dir = Path(args.out).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    browser = SteelSDKBrowser(
        session_name=args.session,
        steel_api_key=os.getenv("STEEL_API_KEY"),
        local=args.local,
        api_url=args.api_url,
        timeout_sec=args.timeout,
    )

    started = False
    try:
        session = browser.start_session()
        started = True
        opened = browser.open_url(args.url)
        snapshot = browser.snapshot(interactive=True)
        screenshot_path = browser.screenshot(str(out_dir / "smoke.png"))

        snapshot_path = out_dir / "snapshot.txt"
        snapshot_path.write_text(snapshot + "\n", encoding="utf-8")

        result = {
            "ok": True,
            "session_id": session.id,
            "mode": session.mode,
            "url": args.url,
            "open_result": opened,
            "snapshot_path": str(snapshot_path),
            "screenshot_path": screenshot_path,
        }
        (out_dir / "result.json").write_text(
            json.dumps(result, indent=2, ensure_ascii=True) + "\n",
            encoding="utf-8",
        )
        print(json.dumps(result, indent=2, ensure_ascii=True))
        return 0
    except Exception as exc:
        result = {
            "ok": False,
            "error": f"{type(exc).__name__}: {exc}",
        }
        (out_dir / "result.json").write_text(
            json.dumps(result, indent=2, ensure_ascii=True) + "\n",
            encoding="utf-8",
        )
        print(json.dumps(result, indent=2, ensure_ascii=True), file=sys.stderr)
        return 1
    finally:
        if started:
            try:
                browser.stop_session()
            except Exception:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
