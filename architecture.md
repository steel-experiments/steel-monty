# Steel Monty Agent Architecture

## Purpose

This project executes browser tasks with a minimal control loop:

1. An LLM generates Python task code.
2. A policy gate validates that code.
3. Monty executes it with an allow-listed helper API.
4. Helpers drive a real Steel browser session via Steel SDK + Playwright CDP.
5. Artifacts are persisted for each attempt and run.

## Design Goals

- Keep orchestration simple and auditable.
- Avoid tool-calling complexity in the model API layer.
- Enforce explicit runtime capability boundaries.
- Preserve reproducibility through deterministic artifacts.

## Module Map

- CLI entrypoint: `src/steel_monty_agent/cli.py`
- Runtime config: `src/steel_monty_agent/config.py`
- Main controller: `src/steel_monty_agent/orchestrator.py`
- LLM integration: `src/steel_monty_agent/llm_anthropic.py`
- Prompt contract: `src/steel_monty_agent/prompts.py`
- Code policy gate: `src/steel_monty_agent/policy.py`
- Monty execution wrapper: `src/steel_monty_agent/monty_runner.py`
- Helper facade + event log: `src/steel_monty_agent/browser_bridge.py`
- Browser runtime client: `src/steel_monty_agent/steel_sdk.py`
- Typed run records: `src/steel_monty_agent/schemas.py`

## High-Level Component Diagram

```mermaid
flowchart TB
    User[User Objective]
    CLI[CLI<br/>cli.py]
    CFG[Settings<br/>config.py]
    ORCH[Orchestrator<br/>orchestrator.py]
    LLM[Anthropic Code Generator<br/>llm_anthropic.py]
    PR[Prompt Builder<br/>prompts.py]
    POL[AST Policy Gate<br/>policy.py]
    MONTY[Monty Runner<br/>monty_runner.py]
    BRIDGE[Browser Bridge<br/>browser_bridge.py]
    SDK[Steel SDK Browser Client<br/>steel_sdk.py]
    STEEL[Steel Session API]
    CDP[Playwright over CDP]
    WEB[Target Website]
    ART[Artifacts<br/>artifacts/runs/<run_id>]

    User --> CLI
    CLI --> CFG
    CLI --> ORCH
    ORCH --> PR
    ORCH --> LLM
    ORCH --> POL
    ORCH --> MONTY
    MONTY --> BRIDGE
    BRIDGE --> SDK
    SDK --> STEEL
    SDK --> CDP
    CDP --> WEB
    ORCH --> ART
    BRIDGE --> ART
```

## Attempt Lifecycle Sequence

```mermaid
sequenceDiagram
    participant U as User
    participant C as CLI
    participant O as Orchestrator
    participant G as LLM Generator
    participant P as Policy Gate
    participant M as Monty Runner
    participant B as Browser Bridge
    participant S as SteelSDKBrowser
    participant A as Artifacts

    U->>C: objective text
    C->>O: run(objective, settings)
    O->>G: generate_program(attempt, prev_error, prev_observation)
    G-->>O: generated code
    O->>A: write prompt/response/program
    O->>P: validate(code)
    P-->>O: pass/fail

    alt policy pass
        O->>M: run(code, external_functions)
        M->>B: call helper functions
        B->>S: start_session/open_url/snapshot/click...
        S-->>B: action results
        B-->>M: helper return values
        M-->>O: execution result
        O->>A: write result.json
    else policy fail or runtime error
        O->>A: write error.txt + failure result.json
    end

    O->>B: stop_session() in finally
    B->>A: write bridge_events.json
    O->>A: write run_summary.json
    O-->>C: structured run outcome
```

## Control Flow State Machine

```mermaid
stateDiagram-v2
    [*] --> Init
    Init --> Generate
    Generate --> Validate
    Validate --> Execute: policy_ok
    Validate --> FailedAttempt: policy_error
    Execute --> Success: run_ok
    Execute --> FailedAttempt: runtime_error
    FailedAttempt --> Retry: attempts_remaining
    FailedAttempt --> FinalFailure: no_attempts_left
    Retry --> Generate
    Success --> Finalize
    FinalFailure --> Finalize
    Finalize --> [*]
```

## Runtime Boundaries

## 1) LLM Boundary

- LLM only returns code text.
- It does not call browser APIs directly.
- Prompts enforce helper function-only behavior.

## 2) Policy Boundary

- AST checks block disallowed syntax and names.
- Only allow-listed calls are permitted.
- Script must use at least one helper function.

## 3) Execution Boundary

- Monty executes generated code.
- Only exposed external helper functions are callable.
- Monty limits constrain duration, memory, allocations, recursion.

## 4) Browser Boundary

- `SteelSDKBrowser` owns real session lifecycle and CDP attach.
- `BrowserBridge` is the callable surface used by Monty code.
- All helper calls are event-logged.

## Helper API Surface (Exposed to Monty)

- Top-level helpers:
- `start_browser(session_name=None, local=False, api_url=None)`
- `emit_result(payload)`
- Browser object methods:
- `open_page(url)`
- `current_page()`
- `close()`
- Page object methods:
- `goto(url)`
- `url()`
- `title()`
- `snapshot(interactive=True)`
- `locator(selector)`
- `click(selector)`
- `fill(selector, value)`
- `text(selector)`
- `attr(selector, attr)`
- `wait_for_text(text)`
- `wait_for_selector(selector)`
- `wait_for_ms(ms)`
- `eval_js(script)`
- `screenshot(path=None)`
- Locator object methods:
- `click()`
- `fill(value)`
- `text()`
- `attr(attr)`
- `wait_visible()`

## Artifact Model

Per attempt:

- `prompt.txt`
- `llm_raw_response.txt`
- `program.py`
- `result.json`
- `bridge_events.json`
- `error.txt` (when applicable)
- `stop_error.txt` (when cleanup fails)

Per run:

- `run_summary.json`

## Failure and Retry Model

- Any generation, validation, execution, or browser error marks attempt failure.
- Failure writes both machine-readable and human-readable artifacts.
- Next attempt receives prior error and last observation hint.
- Orchestrator always attempts browser cleanup in `finally`.

## Data Contracts

Primary normalized result payload:

- `status`: `ok` or `failed`
- `results`: arbitrary result object/list/value
- `evidence`: list of strings
- `errors`: list of strings
- `artifacts`: object with attempt/run metadata

Run summary payload:

- `run_id`
- `objective`
- `success`
- `run_dir`
- `final_result`
- `attempts[]` with per-attempt file references and status

## Security Posture

- Capability-based execution (Monty external function allow-list).
- AST-level pre-execution rejection for risky constructs.
- No direct import/system/network access from generated code.
- Session lifecycle explicitly owned by host runtime, not model code.

## Operational Notes

- Default mode is Steel cloud unless `--local` or API URL override is supplied.
- Use `--cloud` to explicitly override `STEEL_MONTY_LOCAL=true` at runtime.
- Environment and dependencies are managed with `uv`.
- Recommended run path:
  - `uv sync`
  - `uv run steel-monty-agent "<objective>"`
- SDK/browser smoke path:
  - `uv run python scripts/smoke.py`
