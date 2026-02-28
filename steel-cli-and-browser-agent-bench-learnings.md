# Learnings: `~/steel-cli` and `~/browser-agent-bench`

## Quick outcome
- `steel-cli` is a browser-first CLI where top-level commands (`steel browser ...`) are split into native lifecycle commands and passthrough compatibility mode for `agent-browser`-style usage.
- `browser-agent-bench` is a benchmark harness that executes the same prompt families across many tooling scenarios using `codex exec`, enforces JSON output schemas, scores success/consistency, then adds optional LLM judging.

## `~/steel-cli` architecture notes

### Entry and command routing
- `source/steel.tsx` performs `--version`, help handling, browser passthrough dispatch, and optional auto-update behavior before launching Pastel CLI commands.
- `source/utils/browser/routing.ts` determines dispatch mode:
  - native: `steel browser start|stop|sessions|live`
  - passthrough: all other `steel browser ...`
  - special case for `steel browser help`.
- Passthrough command parser is in `source/utils/browser/adapter.ts`, and runtime fallback tries:
  1) `STEEL_BROWSER_RUNTIME_BIN`
  2) vendored runtime manifest
  3) `agent-browser` executable.

### Browser lifecycle and API mode
- `source/utils/browser/lifecycle.ts` owns session creation/listing/stop for cloud vs local mode, including:
  - API base URL precedence (cloud/local env/config)
  - session state lock + persisted JSON (`browser-session-state.json`)
  - `start` attach/reuse behavior, dead session handling, and release/cleanup.
- It supports bootstrap flags forwarded to browser sessions (`--local`, `--api-url`, `--session`, `--proxy`, `--session-timeout`, `--stealth`, `--session-solve-captcha`, etc.) in passthrough mode.
- It resolves `--cdp` passthrough and `--auto-connect` behavior before injecting connect URL injection.
- `source/utils/browser/display.ts` sanitizes connect URLs before display by redacting auth-like query params.

### Local runtime flow
- `source/utils/dev/local.ts` contains repo cloning, docker-compose discovery, and runtime start/stop helpers.
- Command surface:
  - `source/commands/dev/install.tsx`
  - `source/commands/dev/start.tsx`
  - `source/commands/dev/stop.tsx`
- Local behavior includes docker checks, `.config/steel/` repo path management, and `API_PORT` derivation.

### API tools and URL/auth handling
- `source/utils/topLevelTools.ts` is used by:
  - `source/commands/scrape.tsx`
  - `source/commands/screenshot.tsx`
  - `source/commands/pdf.tsx`
- It handles API mode resolution, auth resolution via `resolveBrowserAuth`, JSON parsing, and standardized scrape formatting/order.
- URL normalization is applied for scrape/open commands when host is provided without scheme.

### Native browser commands
- `source/commands/browser/start.tsx`, `stop.tsx`, `sessions.tsx`, `live.tsx` are the native command entrypoints and all use lifecycle utilities.

### Run flow touchpoints (for automation/templates)
- `source/commands/run.tsx` defines the interactive flow and task/template steps.
- `source/components/run/runner.tsx` and `source/components/run/browserrunner.tsx` handle execution + optional local runtime startup for local templates.

## `~/browser-agent-bench` architecture notes

### Core objective and run model
- Single shared benchmark schema across scenarios using repeated Codex executions with strict output contracts.
- Scenario/task matrix is loaded from `bench/scenarios/*.yaml` and `bench/tasks/*.yaml`.

### Orchestration and execution
- `bench/runners/run_all.ts`:
  - Parses many CLI flags (repetitions, concurrency, judge options, timeouts, retries, dry-run).
  - Builds a per-scenario work item list and runs with semaphores (`max_concurrency`, `max_site_concurrency`, `max_steel_concurrency`).
  - Copies isolated workspace for each run and invokes:
    - `codex exec --json --output-schema ...`
    - output capture to per-run `prompt.txt`, `codex.jsonl`, `output.json`, `stderr.log`
    - writes deterministic metric rows (`results/raw/...` and `results/summary/...`).
- `bench/runners/setup.ts` handles source checkout (`vendor/*`) and MCP registration prep.

### Validation and quality scoring
- `bench/schemas/run_output.schema.json`: run output contract (`success`, `results`, `notes`, etc.).
- `bench/runners/summarize_metrics.ts` computes per-run/per-scenario metrics from `metrics.jsonl`.
- `bench/schemas/judge_output.schema.json` + `bench/runners/run_all.ts` judge pass:
  - weighted quality score:
    - task_completion 0.45
    - browsing_effectiveness 0.25
    - result_relevance 0.20
    - constraint_compliance 0.10
  - verdict logic: `true`/`false`/`unclear` (unclear takes precedence on method policy violation).

### Scenario policy controls and method enforcement
- `bench/runners/run_all.ts` encodes method marker detection (Playwright/CDP/MCP/framework markers) and scenario-defined policy constraints.
- Violations are tracked and can force a judge `unclear` verdict.

### Report and comparison tooling
- `bench/runners/compare_runs.ts` enforces regression thresholds between runs.
- `bench/runners/write_narrative_report.ts` builds narrative reports from deterministic summary + failure evidence.

### Scenario/task/config patterns
- Example task prompts:
  - `bench/tasks/task_hotel_nyc_grand_central.yaml`
  - `bench/tasks/task_submit_hcaptcha_form.yaml`
- Example scenario configurations:
  - `bench/scenarios/steel_openapi_raw_hcaptcha.yaml`
  - `bench/scenarios/steel_cli_new_hcaptcha.yaml`
  - `bench/scenarios/agent_browser.yaml`
- Scenario-level constraints and isolation are documented in per-scenario files under `scenario_workspaces/*/AGENTS.md`.

## Notable connection
- `browser-agent-bench` can exercise `steel-cli` behavior directly via constrained scenario definitions, especially those using local Steel CLI + `steel browser start/stop` and `steel browser ...` passthrough flows from the `steel-cli` project.
