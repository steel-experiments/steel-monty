from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .browser_bridge import BrowserBridge
from .config import Settings
from .llm_anthropic import AnthropicCodeGenerator
from .monty_runner import MontyRunner
from .policy import ScriptPolicy
from .schemas import AttemptRecord, OrchestrationResult
from .steel_sdk import SteelSDKBrowser


def _run_id() -> str:
    return datetime.now(UTC).strftime("%Y%m%d_%H%M%S_%f")


class Orchestrator:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.generator = AnthropicCodeGenerator(
            api_key=settings.anthropic_api_key,
            model=settings.anthropic_model,
        )
        self.policy = ScriptPolicy()
        self.monty = MontyRunner(limits=settings.monty_limits.to_limits_dict())

    def with_overrides(
        self,
        *,
        max_attempts: int | None = None,
        steel_local: bool | None = None,
        steel_api_url: str | None = None,
    ) -> "Orchestrator":
        updated = self.settings
        if max_attempts is not None:
            if max_attempts < 1:
                raise ValueError("max_attempts must be >= 1.")
            updated = replace(updated, max_attempts=max_attempts)
        if steel_local is not None:
            updated = replace(updated, steel_local=steel_local)
        if steel_api_url is not None:
            normalized_api_url = steel_api_url.strip() or None
            updated = replace(updated, steel_api_url=normalized_api_url)
        return Orchestrator(updated)

    def run(self, objective: str, session_name: str | None = None) -> OrchestrationResult:
        if not objective.strip():
            raise ValueError("Objective must not be empty.")

        run_id = _run_id()
        run_dir = self.settings.artifacts_root / run_id
        run_dir.mkdir(parents=True, exist_ok=False)

        attempts: list[AttemptRecord] = []
        previous_error: str | None = None
        previous_observation: str | None = None
        final_result: dict[str, Any] | None = None

        for attempt in range(1, self.settings.max_attempts + 1):
            attempt_dir = run_dir / f"attempt_{attempt:02d}"
            attempt_dir.mkdir(parents=True, exist_ok=False)

            prompt_path = attempt_dir / "prompt.txt"
            response_path = attempt_dir / "llm_raw_response.txt"
            program_path = attempt_dir / "program.py"
            result_path = attempt_dir / "result.json"
            events_path = attempt_dir / "bridge_events.json"
            error_path = attempt_dir / "error.txt"

            attempt_session_name = session_name or f"monty-{run_id}-{attempt:02d}"
            bridge: BrowserBridge | None = None
            error_text: str | None = None
            success = False

            try:
                generated = self.generator.generate_program(
                    objective=objective,
                    attempt=attempt,
                    previous_error=previous_error,
                    previous_observation=previous_observation,
                )
                prompt_path.write_text(generated.prompt + "\n", encoding="utf-8")
                response_path.write_text(generated.raw_response + "\n", encoding="utf-8")
                program_path.write_text(generated.code + "\n", encoding="utf-8")

                backend = SteelSDKBrowser(
                    session_name=attempt_session_name,
                    steel_api_key=self.settings.steel_api_key,
                    local=self.settings.steel_local,
                    api_url=self.settings.steel_api_url,
                    timeout_sec=self.settings.browser_timeout_sec,
                )
                bridge = BrowserBridge(backend=backend, run_dir=attempt_dir)

                self.policy.validate(generated.code)
                monty_return = self.monty.run(
                    source_code=generated.code,
                    external_functions=bridge.external_functions(),
                )

                payload = bridge.final_result or self._normalize_result_payload(monty_return)
                payload["artifacts"].setdefault("attempt", attempt)
                payload["artifacts"].setdefault("run_id", run_id)
                payload["artifacts"].setdefault("attempt_dir", str(attempt_dir))

                result_path.write_text(
                    json.dumps(payload, indent=2, ensure_ascii=True, default=str) + "\n",
                    encoding="utf-8",
                )
                final_result = payload
                success = True
            except Exception as exc:
                error_text = f"{type(exc).__name__}: {exc}"
                error_path.write_text(error_text + "\n", encoding="utf-8")
                previous_error = error_text
                previous_observation = bridge.last_observation() if bridge else None

                failure_payload = self._failure_payload(
                    error_text=error_text,
                    run_id=run_id,
                    attempt=attempt,
                    attempt_dir=attempt_dir,
                )
                result_path.write_text(
                    json.dumps(failure_payload, indent=2, ensure_ascii=True, default=str)
                    + "\n",
                    encoding="utf-8",
                )
                final_result = failure_payload
            finally:
                if bridge is not None:
                    try:
                        bridge.stop_session()
                    except Exception as stop_exc:
                        stop_error = f"Session cleanup error: {type(stop_exc).__name__}: {stop_exc}"
                        (attempt_dir / "stop_error.txt").write_text(
                            stop_error + "\n", encoding="utf-8"
                        )
                        if not error_text:
                            error_text = stop_error
                        if success and final_result is not None:
                            errors = final_result.get("errors")
                            if isinstance(errors, list):
                                errors.append(stop_error)
                            else:
                                final_result["errors"] = [stop_error]
                        if not error_path.exists():
                            error_path.write_text(stop_error + "\n", encoding="utf-8")
                    bridge.dump_events(events_path)
                else:
                    events_path.write_text("[]\n", encoding="utf-8")

            attempts.append(
                AttemptRecord(
                    attempt=attempt,
                    success=success,
                    session_name=attempt_session_name,
                    prompt_path=str(prompt_path),
                    response_path=str(response_path),
                    program_path=str(program_path),
                    result_path=str(result_path),
                    events_path=str(events_path),
                    error_path=str(error_path) if error_text else None,
                    error=error_text,
                )
            )

            if success:
                result = OrchestrationResult(
                    run_id=run_id,
                    objective=objective,
                    success=True,
                    run_dir=str(run_dir),
                    final_result=final_result,
                    attempts=attempts,
                )
                self._write_summary(run_dir, result)
                return result

        result = OrchestrationResult(
            run_id=run_id,
            objective=objective,
            success=False,
            run_dir=str(run_dir),
            final_result=final_result,
            attempts=attempts,
        )
        self._write_summary(run_dir, result)
        return result

    @staticmethod
    def _normalize_result_payload(monty_return: Any) -> dict[str, Any]:
        return BrowserBridge.normalize_result_payload(monty_return)

    @staticmethod
    def _failure_payload(
        *,
        error_text: str,
        run_id: str,
        attempt: int,
        attempt_dir: Path,
    ) -> dict[str, Any]:
        return {
            "status": "failed",
            "results": [],
            "evidence": [],
            "errors": [error_text],
            "artifacts": {
                "run_id": run_id,
                "attempt": attempt,
                "attempt_dir": str(attempt_dir),
            },
        }

    @staticmethod
    def _write_summary(run_dir: Path, result: OrchestrationResult) -> None:
        summary_path = run_dir / "run_summary.json"
        summary_path.write_text(
            json.dumps(result.to_dict(), indent=2, ensure_ascii=True, default=str) + "\n",
            encoding="utf-8",
        )
