# LLM + Monty + Steel Minimal Browser Agent

## 1. Objective

Build a minimal, reliable browser agent where:

- An LLM writes full Python task code.
- Code executes in `pydantic-monty` (sandboxed, capability-based runtime).
- Browser actions run through Steel browser sessions.
- No tool-calling framework is required in the model API layer.

The target is a reproducible pipeline that favors simplicity without giving up control, safety, or observability.

## 2. Scope

### In Scope

- Single orchestrator process.
- Anthropic API for code generation and repair.
- Monty execution with explicit external function allow-list.
- Steel-backed browser action bridge.
- Attempt/retry loop with artifact capture.
- JSON output contract for deterministic downstream evaluation.

### Out of Scope (v1)

- Multi-agent delegation.
- Parallel tab/task planning.
- Full autonomous long-horizon memory.
- Rich GUI dashboard.
- Production secrets vault integration.

## 3. Design Principles

1. Keep the model surface small and explicit.
2. Separate control plane and action plane.
3. Default-deny capabilities in execution runtime.
4. Make every run reproducible through persisted artifacts.
5. Keep implementation modular, but use one Steel SDK runtime path end to end.

## 4. System Architecture

## 4.1 Control Plane

- Receives user objective.
- Builds generation prompt and constraints.
- Calls Anthropic model for code.
- Validates generated code with AST policy checks.
- Executes code in Monty with bounded limits.
- Handles retries with failure feedback.
- Persists run artifacts and summary.

## 4.2 Execution Plane

- Monty runs generated Python.
- Only approved external functions are exposed.
- External functions call the browser bridge.

## 4.3 Browser Plane

- Steel session lifecycle + action commands.
- Single runtime path: Steel Python SDK for session lifecycle, Playwright CDP for actions.

## 5. Runtime Contracts

## 5.1 Generated Code Contract

Generated code must:

- Contain no imports.
- Use only approved helper functions and safe built-ins.
- Return a final payload by calling `emit_result(payload)` or by leaving a final expression.
- Keep deterministic structure and avoid unbounded loops.

## 5.2 Exposed Helper API

- `start_session(session_name=None, local=False, api_url=None) -> dict`
- `open_url(url) -> dict`
- `snapshot(interactive=True) -> str`
- `click(target) -> dict`
- `fill(target, value) -> dict`
- `wait_for(text=None, selector=None, ms=None) -> dict`
- `get_text(target) -> str`
- `get_attr(target, attr) -> str`
- `get_url() -> str`
- `eval_js(script) -> str`
- `screenshot(path=None) -> str`
- `emit_result(payload) -> dict`
- `stop_session() -> dict`

## 5.3 Output Schema (logical)

Top-level expected keys:

- `status`: `"ok"` or `"failed"`
- `results`: list or object
- `evidence`: list of short evidence strings
- `errors`: list of non-fatal issues
- `artifacts`: dict of artifact references

If model code does not call `emit_result`, orchestrator wraps the final expression into this schema shape.

## 6. Safety Model

## 6.1 AST Policy Guard

Reject scripts containing:

- `import` / `from ... import ...`
- `class` declarations
- `with` / `async with`
- `try` blocks
- `global` / `nonlocal`
- disallowed names (`eval`, `exec`, `open`, `compile`, `__import__`, etc.)

Additional checks:

- Max AST node budget.
- At least one helper API call must be present.
- Disallow dunder attribute calls.

## 6.2 Monty Guardrails

Use Monty `ResourceLimits`:

- `max_duration_secs`
- `max_memory`
- `max_allocations`
- `max_recursion_depth`

Only explicit external functions are available.

## 6.3 Steel Session Discipline

- Use a deterministic session name per attempt.
- Keep one mode per run (`cloud` default, `local` optional).
- Always attempt cleanup via `stop_session()` in orchestrator `finally`.

## 7. Retry and Recovery

Per attempt:

1. Generate code.
2. Validate policy.
3. Execute in Monty.
4. Capture result or error artifacts.

On failure:

- Feed prior error and optional observation hints into next generation prompt.
- Cap attempts with configurable maximum.

## 8. Artifacts and Observability

For each attempt:

- `prompt.txt`
- `llm_raw_response.txt`
- `program.py`
- `error.txt` (if any)
- `result.json` (on success or normalized fallback)
- `bridge_events.json`

Per run:

- `run_summary.json`

## 9. Benchmark Alignment

The design aligns to benchmark method-policy constraints by:

- Keeping method signatures explicit.
- Persisting deterministic outputs and traces.
- Allowing scenario-specific prompts and references to be injected later.

Future integration adds a small adapter to emit benchmark-compatible fields directly.

## 10. Implementation Plan

## Phase 1: Foundations (this implementation pass)

- Create Python package skeleton.
- Add configuration and schema dataclasses.
- Add Anthropic code generation client.
- Add prompt templates and extraction utilities.
- Add AST policy validator.
- Add Steel SDK backend and browser bridge.
- Add Monty runner and orchestrator.
- Add CLI entrypoint and README.

## Phase 2: Robustness

- Add stronger failure classification.
- Add optional async external function support via `run_monty_async`.
- Add richer evidence extraction and screenshot linkage.
- Add scenario prompt injection for benchmark tasks.

## 11. Acceptance Criteria

- End-to-end run completes for at least one real browsing task.
- No direct imports in generated code pass validation.
- Session start/stop attempts are visible in bridge events.
- Failed runs still emit `run_summary.json` and failure artifacts.
- All external helper calls are auditable in event logs.

## 12. Project File Map (v1)

- `specification.md`
- `pyproject.toml`
- `README.md`
- `schemas/run_result.schema.json`
- `src/steel_monty_agent/config.py`
- `src/steel_monty_agent/schemas.py`
- `src/steel_monty_agent/prompts.py`
- `src/steel_monty_agent/llm_anthropic.py`
- `src/steel_monty_agent/policy.py`
- `src/steel_monty_agent/steel_sdk.py`
- `src/steel_monty_agent/browser_bridge.py`
- `src/steel_monty_agent/monty_runner.py`
- `src/steel_monty_agent/orchestrator.py`
- `src/steel_monty_agent/cli.py`

## 13. Tooling Standard

- Use Astral `uv` as the default environment and dependency workflow.
- Standard commands:
  - `uv sync`
  - `uv run steel-monty-agent "<objective>"`
