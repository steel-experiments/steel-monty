# Pydantic Monty: Source Research Summary

## Sources fetched
- Article: `https://pydantic.dev/articles/pydantic-monty?v=1&utm_source=linkedin`
- Saved article text: `/home/agent/steel-monty/research/pydantic-monty/pydantic-monty-article.txt`
- Saved article HTML: `/home/agent/steel-monty/research/pydantic-monty/pydantic-monty-article.html`
- Package artifacts:
  - Wheel: `/tmp/pydantic-monty-artifacts/pydantic_monty-0.0.7-cp312-cp312-manylinux_2_17_x86_64.manylinux2014_x86_64.whl`
  - Extracted package: `/home/agent/steel-monty/research/pydantic-monty/pydantic_monty`
  - Metadata: `/home/agent/steel-monty/research/pydantic-monty/pydantic_monty-0.0.7.dist-info/METADATA`

## Key package-level findings (`pydantic-monty` 0.0.7)

### Packaging / identity
- Name and release confirmed in wheel metadata: `pydantic-monty` `0.0.7`, alpha (`development status 3`) and requires Python `>=3.10`.
- Homepage/source: `https://github.com/pydantic/monty/`.
- See `/home/agent/steel-monty/research/pydantic-monty/pydantic_monty-0.0.7.dist-info/METADATA:2-4`.

### Public Python API surface
- Top-level exports include:
  - `Monty`, `MontyRepl`, `MontyComplete`, `MontySnapshot`, `MontyFutureSnapshot`
  - errors: `MontyError`, `MontySyntaxError`, `MontyRuntimeError`, `MontyTypingError`
  - filesystem interfaces: `AbstractOS`, `AbstractFile`, `MemoryFile`, `CallbackFile`, `OSAccess`, `StatResult`, `OsFunction`
  - async helper: `run_monty_async`
  - limits/result helpers: `ResourceLimits`, `ExternalResult`
- See `/home/agent/steel-monty/research/pydantic-monty/pydantic_monty/__init__.py:24-49`.

### `run_monty_async`
- Asynchronously drives `Monty.start()` and handles:
  - OS function snapshots via provided `os` callback (`Path`-style calls)
  - external functions (sync and async)
  - future-based external calls (`future=...` -> waits with `asyncio.FIRST_COMPLETED`)
- Cancels outstanding tasks on exit and swallows `CancelledError` from final gather.
- See `/home/agent/steel-monty/research/pydantic-monty/pydantic_monty/__init__.py:53-149`.

### `ResourceLimits`
- Optional typed dict keys:
  - `max_allocations`, `max_duration_secs`, `max_memory`, `gc_interval`, `max_recursion_depth`.
- See `/home/agent/steel-monty/research/pydantic-monty/pydantic_monty/__init__.py:169-189`.

### `Monty` / runtime behavior (stub surface)
- `Monty` is instantiated from source and configured via:
  - `code`, `script_name`, `inputs`, `external_functions`, `type_check`, `type_check_stubs`, `dataclass_registry`.
- Supports `run()`, `start()`, `dump()`, `load()`, `register_dataclass()`.
- Snapshot flow is first-class (`start`/`resume`) with `MontySnapshot` and `MontyFutureSnapshot` for async orchestration.
- `MontyRepl` supports persistent incremental execution via `create(...)->(repl, output)` and `feed`.
- Exception hierarchy: all inherit from `MontyError`.
- See `/home/agent/steel-monty/research/pydantic-monty/pydantic_monty/_monty.pyi:24-210` and `...:260-520` for snapshot/exception details.

### Filesystem sandbox model (`os_access.py`)
- `OsFunction` whitelist includes `Path.exists`, `Path.is_file`, `Path.read_text`, `Path.write_text`, `Path.mkdir`, `Path.stat`, `Path.resolve`, `os.getenv`, `os.environ`.
- `OSAccess` implements an in-memory virtual filesystem (memory-only by default):
  - controlled path traversal within virtual tree
  - file APIs for exists/is_file/is_dir/read/write/iterdir/stat/rename/rmdir/unlink etc.
  - explicit environment isolation via provided `environ`
- `MemoryFile` is the intended secure in-memory option.
- `CallbackFile` can execute host callbacks and explicitly warned as non-sandbox-safe.
- See `/home/agent/steel-monty/research/pydantic-monty/pydantic_monty/os_access.py:13-32`, `...:111-174`, `...:479-547`, `...:553-639`, `...:643-863`.

## Article-derived learnings (as read)

Article title/date/author: *Pydantic Monty: you probably don't need a full sandbox* (Samuel Colvin, `2026/02/27`).
- See `/home/agent/steel-monty/research/pydantic-monty/pydantic-monty-article.txt:1-30`.

### Core framing
- The article positions Monty as a middle ground “right of tool calling” on an execution-approach continuum from tool calling to full computer use.
- Core term used is “CodeMode”: model writes Python and executes through explicit external functions.
- See `/home/agent/steel-monty/research/pydantic-monty/pydantic-monty-article.txt:50-67`.

### “Start Left, Move Right” model
- Contrasts Monty with “start with full environment then restrict” sandboxing.
- Monty model is explicit allow-list: start with zero access and add capabilities intentionally.
- Emphasis on default-deny for filesystem/network/env vars and audited capability add-on.
- See `/home/agent/steel-monty/research/pydantic-monty/pydantic-monty-article.txt:92-99`.

### What Monty is and capabilities
- Rust implementation of its own bytecode VM (not restricted CPython / not WASM).
- Supports sync+async functions, closures, comprehensions, f-strings, core typing features, select stdlib modules; external calls; snapshotting; type checking; resource limits; REPL assumptions.
- Does not yet support classes, match statements, context managers, full stdlib, and likely no third-party packages.
- See `/home/agent/steel-monty/research/pydantic-monty/pydantic-monty-article.txt:101-134`.

### Practical claims
- Latency comparisons in the article claim microsecond-ish start for Monty versus ms+ for containers and much slower approaches.
- Cost is framed as in-process execution (no per-run infra) and tiny snapshots.
- Setup is “`pip install`/`uv add` + `npm install @pydantic/monty`” for Python/JS.
- See `/home/agent/steel-monty/research/pydantic-monty/pydantic-monty-article.txt:196-224`.

### Examples in the article
- Weather agent example contrasts tool-calling round trips vs one-block CodeMode script.
  - Reported tool-calling example: longer flow and higher token/latency profile than CodeMode.
  - CodeMode example cuts to fewer LLM calls and fewer tokens.
  - See `/home/agent/steel-monty/research/pydantic-monty/pydantic-monty-article.txt:390-500`.
- Web scraping example shows exposing typed facades such as `Tag`/`Page` wrappers instead of passing heavy external objects directly.
  - Mentions `BeautifulSoup` and Playwright integration pattern with persistent browser state.
  - See `/home/agent/steel-monty/research/pydantic-monty/pydantic-monty-article.txt:506-845`.

### Risks / follow-up notes from the article
- Author asks for security reports and for users to report missing Python behaviors they need.
- Mentions explicit maturity caveat: project is early.
- See `/home/agent/steel-monty/research/pydantic-monty/pydantic-monty-article.txt:846-854`.

## Output check
- I fetched both requested assets successfully and saved the markdown summary.
- Artifact path: `/home/agent/steel-monty/research/pydantic-monty-summary.md`.
