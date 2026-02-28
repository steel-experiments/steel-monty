from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass
class GeneratedProgram:
    prompt: str
    raw_response: str
    code: str


@dataclass
class AttemptRecord:
    attempt: int
    success: bool
    session_name: str
    prompt_path: str
    response_path: str
    program_path: str
    result_path: str | None
    events_path: str | None
    error_path: str | None
    error: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class OrchestrationResult:
    run_id: str
    objective: str
    success: bool
    run_dir: str
    final_result: dict[str, Any] | None
    attempts: list[AttemptRecord]

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "objective": self.objective,
            "success": self.success,
            "run_dir": self.run_dir,
            "final_result": self.final_result,
            "attempts": [attempt.to_dict() for attempt in self.attempts],
        }
