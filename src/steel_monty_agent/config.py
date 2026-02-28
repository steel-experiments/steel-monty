from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _env_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


def _env_int(value: str | None, default: int) -> int:
    if value is None:
        return default
    try:
        parsed = int(value)
    except ValueError:
        return default
    return parsed if parsed > 0 else default


@dataclass(frozen=True)
class MontyLimitConfig:
    max_duration_secs: int = 45
    max_memory: int = 128 * 1024 * 1024
    max_allocations: int = 5_000_000
    max_recursion_depth: int = 256

    def to_limits_dict(self) -> dict[str, int]:
        return {
            "max_duration_secs": self.max_duration_secs,
            "max_memory": self.max_memory,
            "max_allocations": self.max_allocations,
            "max_recursion_depth": self.max_recursion_depth,
        }


@dataclass(frozen=True)
class Settings:
    anthropic_api_key: str
    anthropic_model: str
    max_attempts: int
    browser_timeout_sec: int
    artifacts_root: Path
    steel_api_key: str | None
    steel_local: bool
    steel_api_url: str | None
    monty_limits: MontyLimitConfig

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> "Settings":
        resolved_env = env if env is not None else dict(os.environ)

        api_key = resolved_env.get("ANTHROPIC_API_KEY", "").strip()
        if not api_key:
            raise ValueError("Missing ANTHROPIC_API_KEY.")

        model = resolved_env.get("ANTHROPIC_MODEL", "claude-3-7-sonnet-latest").strip()
        if not model:
            model = "claude-3-7-sonnet-latest"
        max_attempts = _env_int(resolved_env.get("STEEL_MONTY_MAX_ATTEMPTS"), 3)
        browser_timeout_sec = _env_int(resolved_env.get("STEEL_MONTY_BROWSER_TIMEOUT_SEC"), 30)
        steel_api_key = resolved_env.get("STEEL_API_KEY", "").strip() or None
        steel_local = _env_bool(resolved_env.get("STEEL_MONTY_LOCAL"), False)
        steel_api_url = resolved_env.get("STEEL_MONTY_API_URL")
        steel_api_url = steel_api_url.strip() if steel_api_url else None

        artifacts_root_raw = resolved_env.get("STEEL_MONTY_ARTIFACTS_DIR", "artifacts/runs").strip()
        artifacts_root = Path(artifacts_root_raw).expanduser()
        if not artifacts_root.is_absolute():
            artifacts_root = Path.cwd() / artifacts_root

        monty_limits = MontyLimitConfig(
            max_duration_secs=_env_int(
                resolved_env.get("STEEL_MONTY_LIMIT_MAX_DURATION_SECS"),
                45,
            ),
            max_memory=_env_int(
                resolved_env.get("STEEL_MONTY_LIMIT_MAX_MEMORY"),
                128 * 1024 * 1024,
            ),
            max_allocations=_env_int(
                resolved_env.get("STEEL_MONTY_LIMIT_MAX_ALLOCATIONS"),
                5_000_000,
            ),
            max_recursion_depth=_env_int(
                resolved_env.get("STEEL_MONTY_LIMIT_MAX_RECURSION_DEPTH"),
                256,
            ),
        )

        return cls(
            anthropic_api_key=api_key,
            anthropic_model=model,
            max_attempts=max_attempts,
            browser_timeout_sec=browser_timeout_sec,
            artifacts_root=artifacts_root,
            steel_api_key=steel_api_key,
            steel_local=steel_local,
            steel_api_url=steel_api_url,
            monty_limits=monty_limits,
        )
