from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .prompts import SYSTEM_PROMPT, build_generation_prompt, extract_python_code
from .schemas import GeneratedProgram


@dataclass
class AnthropicCodeGenerator:
    api_key: str
    model: str
    max_tokens: int = 2200
    temperature: float = 0.0
    _client_instance: Any | None = field(default=None, init=False, repr=False)

    def _client(self) -> Any:
        if self._client_instance is not None:
            return self._client_instance

        try:
            from anthropic import Anthropic
        except ImportError as exc:
            raise RuntimeError(
                "Missing anthropic package. Install dependencies with `uv sync`."
            ) from exc

        self._client_instance = Anthropic(api_key=self.api_key)
        return self._client_instance

    def generate_program(
        self,
        objective: str,
        attempt: int,
        previous_error: str | None = None,
        previous_observation: str | None = None,
    ) -> GeneratedProgram:
        prompt = build_generation_prompt(
            objective=objective,
            attempt=attempt,
            previous_error=previous_error,
            previous_observation=previous_observation,
        )

        client = self._client()
        try:
            message = client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )
        except Exception as exc:
            raise RuntimeError(f"Anthropic generation failed on attempt {attempt}: {exc}") from exc

        text_parts: list[str] = []
        for block in message.content:
            text = getattr(block, "text", None)
            if isinstance(text, str):
                text_parts.append(text)

        raw_response = "\n".join(text_parts).strip()
        code = extract_python_code(raw_response)
        if not code:
            raise RuntimeError("Model returned an empty program.")

        return GeneratedProgram(prompt=prompt, raw_response=raw_response, code=code)
