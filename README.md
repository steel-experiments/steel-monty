# steel-monty-agent

Minimal implementation of the architecture:

- LLM generates full Python task code.
- Code runs inside Monty with explicit external functions.
- External functions execute browser actions through Steel SDK sessions + Playwright CDP.

## Setup

1. Install dependencies:

```bash
uv sync
```

2. Ensure required environment variables are set:

```bash
export ANTHROPIC_API_KEY=...
export STEEL_API_KEY=...
```

Optional runtime configuration:

```bash
export STEEL_MONTY_MAX_ATTEMPTS=3
export STEEL_MONTY_BROWSER_TIMEOUT_SEC=30
export STEEL_MONTY_ARTIFACTS_DIR=artifacts/runs
export STEEL_MONTY_LOCAL=false
export STEEL_MONTY_API_URL=
```

## Run

```bash
uv run steel-monty-agent "Open example.com and return the page title."
```

Artifacts are written under `artifacts/runs/<run_id>/`.

## Notes

- v1 uses a single Steel SDK runtime path.
- Generated code is checked by an AST policy guard before execution.
