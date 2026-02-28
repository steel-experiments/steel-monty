from __future__ import annotations

import json
import time
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import logfire

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
    @staticmethod
    def _fmt_duration(seconds: float) -> str:
        return f"{seconds:.2f}s"

    @staticmethod
    def _round_timings(timings: dict[str, float]) -> dict[str, float]:
        return {k: round(v, 3) for k, v in timings.items()}

    @staticmethod
    def _extract_errors(payload: dict[str, Any]) -> list[str]:
        errors = payload.get("errors")
        if isinstance(errors, list):
            return [str(item) for item in errors]
        if errors is None:
            return []
        return [str(errors)]

    @staticmethod
    def _is_success_payload(payload: dict[str, Any]) -> bool:
        if not isinstance(payload, dict):
            return False
        status = payload.get("status")
        normalized_status = status.strip().lower() if isinstance(status, str) else ""
        if normalized_status != "ok":
            return False
        return len(Orchestrator._extract_errors(payload)) == 0

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
        steel_solve_captcha: bool | None = None,
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
        if steel_solve_captcha is not None:
            updated = replace(updated, steel_solve_captcha=steel_solve_captcha)
        return Orchestrator(updated)

    @staticmethod
    def _attach_timings(payload: dict[str, Any], timings: dict[str, float]) -> None:
        artifacts = payload.get("artifacts")
        if not isinstance(artifacts, dict):
            artifacts = {}
            payload["artifacts"] = artifacts
        artifacts["timings"] = Orchestrator._round_timings(dict(timings))

    @staticmethod
    def _attach_session_artifacts(
        payload: dict[str, Any],
        *,
        bridge: BrowserBridge,
        attempt: int,
        session_tracker: dict[str, Any],
    ) -> None:
        artifacts = payload.get("artifacts")
        if not isinstance(artifacts, dict):
            artifacts = {}
            payload["artifacts"] = artifacts

        session_info = bridge.active_session_info()
        if session_info is None:
            return

        session_id = session_info.id.strip()
        if not session_id:
            return

        if session_id != session_tracker.get("id"):
            session_tracker["id"] = session_id
            session_tracker["started_attempt"] = attempt

        started_attempt_raw = session_tracker.get("started_attempt")
        started_attempt = (
            int(started_attempt_raw)
            if isinstance(started_attempt_raw, int)
            else attempt
        )

        session_artifact: dict[str, Any] = {
            "id": session_id,
            "mode": session_info.mode,
            "name": session_info.name,
            "live_url": session_info.live_url,
            "persisted": attempt > started_attempt,
        }
        if attempt > started_attempt:
            session_artifact["resumed_from_attempt"] = started_attempt
        artifacts["session"] = session_artifact

    def run(self, objective: str, session_name: str | None = None) -> OrchestrationResult:
        if not objective.strip():
            raise ValueError("Objective must not be empty.")

        run_id = _run_id()
        logfire.info(
            "Run started",
            run_id=run_id,
            objective=objective,
            max_attempts=self.settings.max_attempts,
            steel_local=self.settings.steel_local,
        )
        run_dir = self.settings.artifacts_root / run_id
        run_dir.mkdir(parents=True, exist_ok=False)
        run_session_name = session_name or f"monty-{run_id}"
        backend = SteelSDKBrowser(
            session_name=run_session_name,
            steel_api_key=self.settings.steel_api_key,
            local=self.settings.steel_local,
            api_url=self.settings.steel_api_url,
            timeout_sec=self.settings.browser_timeout_sec,
            solve_captcha=self.settings.steel_solve_captcha,
        )
        bridge = BrowserBridge(backend=backend, run_dir=run_dir)

        attempts: list[AttemptRecord] = []
        previous_error: str | None = None
        previous_observation: str | None = None
        final_result: dict[str, Any] | None = None
        final_result_path: Path | None = None
        run_success = False
        session_tracker: dict[str, Any] = {"id": None, "started_attempt": None}

        try:
            for attempt in range(1, self.settings.max_attempts + 1):
                attempt_started = time.perf_counter()
                attempt_dir = run_dir / f"attempt_{attempt:02d}"
                attempt_dir.mkdir(parents=True, exist_ok=False)
                bridge.set_run_dir(attempt_dir)
                bridge.begin_attempt()
                events_start_index = bridge.event_count()

                prompt_path = attempt_dir / "prompt.txt"
                response_path = attempt_dir / "llm_raw_response.txt"
                program_path = attempt_dir / "program.py"
                result_path = attempt_dir / "result.json"
                events_path = attempt_dir / "bridge_events.json"
                error_path = attempt_dir / "error.txt"

                error_text: str | None = None
                attempt_success = False
                timings: dict[str, float] = {}

                print(f"\nAttempt {attempt}/{self.settings.max_attempts}...", flush=True)
                with logfire.span(
                    "Attempt",
                    run_id=run_id,
                    attempt=attempt,
                    session_name=run_session_name,
                ):
                    try:
                        print("1/3 LLM: generating plan...", flush=True)
                        llm_started = time.perf_counter()
                        generated = self.generator.generate_program(
                            objective=objective,
                            attempt=attempt,
                            previous_error=previous_error,
                            previous_observation=previous_observation,
                        )
                        timings["llm_response_sec"] = time.perf_counter() - llm_started
                        print(
                            f"LLM response done in {self._fmt_duration(timings['llm_response_sec'])}",
                            flush=True,
                        )
                        logfire.info(
                            "LLM response complete",
                            run_id=run_id,
                            attempt=attempt,
                            llm_response_sec=timings["llm_response_sec"],
                        )

                        prompt_path.write_text(generated.prompt + "\n", encoding="utf-8")
                        response_path.write_text(generated.raw_response + "\n", encoding="utf-8")
                        program_path.write_text(generated.code + "\n", encoding="utf-8")

                        print("2/3 Policy: validating generated code...", flush=True)
                        policy_started = time.perf_counter()
                        self.policy.validate(generated.code)
                        timings["policy_validation_sec"] = time.perf_counter() - policy_started
                        print(
                            f"Policy check done in {self._fmt_duration(timings['policy_validation_sec'])}",
                            flush=True,
                        )
                        logfire.info(
                            "Policy validation complete",
                            run_id=run_id,
                            attempt=attempt,
                            policy_validation_sec=timings["policy_validation_sec"],
                        )

                        print("3/3 Execution: running generated code...", flush=True)
                        exec_started = time.perf_counter()
                        monty_return = self.monty.run(
                            source_code=generated.code,
                            external_functions=bridge.external_functions(),
                        )
                        timings["code_execution_sec"] = time.perf_counter() - exec_started
                        print(
                            f"Code execution done in {self._fmt_duration(timings['code_execution_sec'])}",
                            flush=True,
                        )
                        logfire.info(
                            "Code execution complete",
                            run_id=run_id,
                            attempt=attempt,
                            code_execution_sec=timings["code_execution_sec"],
                        )

                        payload = bridge.final_result or self._normalize_result_payload(monty_return)
                        payload["artifacts"].setdefault("attempt", attempt)
                        payload["artifacts"].setdefault("run_id", run_id)
                        payload["artifacts"].setdefault("attempt_dir", str(attempt_dir))
                        self._attach_session_artifacts(
                            payload,
                            bridge=bridge,
                            attempt=attempt,
                            session_tracker=session_tracker,
                        )
                        self._attach_timings(payload, timings)

                        result_path.write_text(
                            json.dumps(payload, indent=2, ensure_ascii=True, default=str) + "\n",
                            encoding="utf-8",
                        )
                        final_result = payload
                        final_result_path = result_path

                        attempt_success = self._is_success_payload(payload)
                        if not attempt_success:
                            errors = self._extract_errors(payload)
                            error_text = (
                                "; ".join(errors)
                                if errors
                                else f"Task reported status: {payload.get('status')}"
                            )
                            error_path.write_text(error_text + "\n", encoding="utf-8")
                            previous_error = error_text
                            previous_observation = bridge.retry_observation_hint()
                            print(f"Attempt failed: {error_text}", flush=True)
                            logfire.error(
                                "Attempt failed",
                                run_id=run_id,
                                attempt=attempt,
                                error=error_text,
                            )
                        else:
                            previous_error = None
                            previous_observation = None
                    except Exception as exc:
                        error_text = f"{type(exc).__name__}: {exc}"
                        print(f"Attempt failed: {error_text}", flush=True)
                        logfire.error(
                            "Attempt failed",
                            run_id=run_id,
                            attempt=attempt,
                            error=error_text,
                        )
                        error_path.write_text(error_text + "\n", encoding="utf-8")
                        previous_error = error_text
                        previous_observation = bridge.retry_observation_hint()

                        timings["attempt_failed_after_sec"] = time.perf_counter() - attempt_started
                        failure_payload = self._failure_payload(
                            error_text=error_text,
                            run_id=run_id,
                            attempt=attempt,
                            attempt_dir=attempt_dir,
                        )
                        self._attach_session_artifacts(
                            failure_payload,
                            bridge=bridge,
                            attempt=attempt,
                            session_tracker=session_tracker,
                        )
                        self._attach_timings(failure_payload, timings)
                        result_path.write_text(
                            json.dumps(failure_payload, indent=2, ensure_ascii=True, default=str)
                            + "\n",
                            encoding="utf-8",
                        )
                        final_result = failure_payload
                        final_result_path = result_path
                    finally:
                        timings["attempt_total_sec"] = time.perf_counter() - attempt_started
                        if final_result is not None:
                            self._attach_timings(final_result, timings)
                        bridge.dump_events(events_path, start_index=events_start_index)

                attempts.append(
                    AttemptRecord(
                        attempt=attempt,
                        success=attempt_success,
                        session_name=run_session_name,
                        prompt_path=str(prompt_path),
                        response_path=str(response_path),
                        program_path=str(program_path),
                        result_path=str(result_path),
                        events_path=str(events_path),
                        error_path=str(error_path) if error_text else None,
                        error=error_text,
                    )
                )

                if attempt_success:
                    run_success = True
                    print(
                        f"Attempt {attempt} complete in {self._fmt_duration(timings['attempt_total_sec'])}",
                        flush=True,
                    )
                    logfire.info(
                        "Attempt succeeded",
                        run_id=run_id,
                        attempt=attempt,
                        attempt_total_sec=timings["attempt_total_sec"],
                    )
                    break

                print(
                    f"Attempt {attempt} failed after {self._fmt_duration(timings['attempt_total_sec'])}",
                    flush=True,
                )
                logfire.info(
                    "Attempt finished with failure",
                    run_id=run_id,
                    attempt=attempt,
                    attempt_total_sec=timings["attempt_total_sec"],
                )
        finally:
            try:
                bridge.stop_session()
            except Exception as stop_exc:
                stop_error = f"Session cleanup error: {type(stop_exc).__name__}: {stop_exc}"
                (run_dir / "stop_error.txt").write_text(stop_error + "\n", encoding="utf-8")
                if final_result is not None:
                    errors = final_result.get("errors")
                    if isinstance(errors, list):
                        errors.append(stop_error)
                    else:
                        final_result["errors"] = [stop_error]
                if final_result is not None and final_result_path is not None:
                    final_result_path.write_text(
                        json.dumps(final_result, indent=2, ensure_ascii=True, default=str) + "\n",
                        encoding="utf-8",
                    )
                logfire.error(
                    "Session cleanup error",
                    run_id=run_id,
                    error=stop_error,
                )

        result = OrchestrationResult(
            run_id=run_id,
            objective=objective,
            success=run_success,
            run_dir=str(run_dir),
            final_result=final_result,
            attempts=attempts,
        )
        self._write_summary(run_dir, result)
        logfire.info("Run finished", run_id=run_id, success=result.success)
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
