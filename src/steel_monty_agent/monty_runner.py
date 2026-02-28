from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


class MontyExecutionError(RuntimeError):
    pass


@dataclass
class MontyRunner:
    limits: dict[str, int] | None = None
    type_check: bool = False

    def run(
        self,
        source_code: str,
        external_functions: dict[str, Callable[..., Any]],
    ) -> Any:
        try:
            from pydantic_monty import Monty
        except ImportError as exc:
            raise MontyExecutionError(
                "Missing pydantic-monty package. Install dependencies with `uv sync`."
            ) from exc

        try:
            monty = Monty(
                source_code,
                external_functions=sorted(external_functions.keys()),
                type_check=self.type_check,
            )
            return monty.run(
                limits=self.limits,
                external_functions=external_functions,
            )
        except Exception as exc:
            raise MontyExecutionError(str(exc)) from exc
