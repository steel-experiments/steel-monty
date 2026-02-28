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

### Logfire Setup (`stell-monty`)

1. Install the SDK:

```bash
uv add logfire
```

2. Authenticate your local environment:

```bash
uv run logfire auth
```

Credentials are stored in `~/.logfire/default.toml`.

3. Set the Logfire project from this repo directory:

```bash
uv run logfire projects use stell-monty
```

This creates `.logfire/` in the working directory and stores the project token locally.
No `LOGFIRE_TOKEN` env var is required when using this flow.

Config priority: `.env` first, then environment variables only for missing keys.

If a key is set in both places, `.env` is used.

Run-time logs:

- `Attempt X/Y...` shows overall progress.
- `LLM response done in ...` shows model call time.
- `Steel session ready in ...` shows session connect time.
- `Code execution done in ...` shows generated code runtime.
- Timings are also written into each attempt artifact as `artifacts.timings`.
- Logfire is configured automatically at CLI startup (`logfire.configure(...)`).

Optional runtime configuration:

```bash
export STEEL_MONTY_MAX_ATTEMPTS=3
export STEEL_MONTY_BROWSER_TIMEOUT_SEC=30
export STEEL_MONTY_ARTIFACTS_DIR=artifacts/runs
export STEEL_MONTY_LOCAL=false
export STEEL_MONTY_API_URL=
export STEEL_MONTY_SOLVE_CAPTCHA=false
```

For sites with production CAPTCHA widgets (like the hCaptcha sample), set:

```bash
export STEEL_MONTY_SOLVE_CAPTCHA=true
```

or pass `--solve-captcha` on the command line.

Runtime mode override flags:

- Use `--local` to force local Steel mode for a run.
- Use `--cloud` to force cloud mode even when `STEEL_MONTY_LOCAL=true`.

## Run

```bash
uv run steel-monty-agent "Open example.com and return the page title."
```

Explicitly force cloud mode:

```bash
uv run steel-monty-agent --cloud "Open example.com and return the page title."
```

## Persistent Session Showcase

Retries now reuse one Steel browser session for the full run.

- Attempt 2+ can continue from the page state created by prior attempts.
- Session cleanup happens once at the end of the run.
- Attempt `result.json` includes `artifacts.session` metadata (session id and resume origin when reused).

## Object API Shape

Generated Monty code now uses an object-shaped browser surface:

- Top-level helpers: `start_browser(...)`, `emit_result(payload)`
- Browser methods: `open_page(url)`, `current_page()`, `close()`
- Page methods: `goto(url)`, `url()`, `title()`, `snapshot()`, `locator(selector)`, `eval_js(script)`, `screenshot()`
- Locator methods: `click()`, `fill(value)`, `text()`, `attr(name)`, `wait_visible()`

Artifacts are written under `artifacts/runs/<run_id>/`.

## Notes

- v1 uses a single Steel SDK runtime path.
- Generated code is checked by an AST policy guard before execution.
