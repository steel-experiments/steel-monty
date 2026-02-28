from __future__ import annotations

import sys

import logfire

_CONFIGURED = False


def configure_logfire() -> bool:
    global _CONFIGURED
    if _CONFIGURED:
        return True

    try:
        logfire.configure()
    except Exception as exc:
        print(f"Logfire disabled: {exc}", file=sys.stderr)
        return False

    _CONFIGURED = True
    logfire.info("Logfire configured", app="steel-monty-agent")
    return True
