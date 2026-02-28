from __future__ import annotations

import re


SYSTEM_PROMPT = """You generate Python code that runs inside a restricted Monty runtime.

Return only one Python code block.
Do not add explanation text before or after the code block.

Runtime constraints:
- No imports.
- No class definitions.
- No async/await.
- No while loops.
- Do not use eval/exec/open/compile/__import__.
- Keep code short and deterministic.

You can only call these top-level helper functions:
- start_browser(session_name=None, local=False, api_url=None)
- emit_result(payload)

`start_browser(...)` returns a Browser object with methods:
- browser.open_page(url) -> Page
- browser.current_page() -> Page
- browser.close()

Page methods:
- page.goto(url)
- page.url()
- page.title()
- page.snapshot(interactive=True)
- page.locator(selector) -> Locator
- page.click(selector)
- page.fill(selector, value)
- page.text(selector)
- page.attr(selector, attr)
- page.wait_for_text(text)
- page.wait_for_selector(selector)
- page.wait_for_ms(ms)
- page.eval_js(script)
- page.screenshot(path=None)

Locator methods:
- locator.click()
- locator.fill(value)
- locator.text()
- locator.attr(attr)
- locator.wait_visible()

Required output behavior:
- Always call emit_result(payload) with a dict payload.
- Payload should include keys: status, results, evidence, errors, artifacts.
- Use status="ok" unless the task clearly failed.

Selector strategy:
- Prefer page.snapshot(interactive=True) first.
- Use stable CSS selectors.
- Keep actions minimal and goal-focused.
"""


CODE_BLOCK_PATTERN = re.compile(r"```python\s*(.*?)```", re.DOTALL | re.IGNORECASE)
GENERIC_CODE_BLOCK_PATTERN = re.compile(r"```\s*(.*?)```", re.DOTALL)


def build_generation_prompt(
    objective: str,
    attempt: int,
    previous_error: str | None = None,
    previous_observation: str | None = None,
) -> str:
    sections = [
        f"Objective:\n{objective.strip()}",
        f"Attempt number: {attempt}",
        (
            "Execution requirements:\n"
            "- Start a browser early with start_browser(...).\n"
            "- Perform only needed actions.\n"
            "- Close the browser with browser.close() before finishing.\n"
            "- Call emit_result(payload) at the end."
        ),
    ]

    if previous_error:
        sections.append(f"Previous attempt error:\n{previous_error.strip()}")
    if previous_observation:
        sections.append(
            "Previous observation hint:\n"
            f"{previous_observation.strip()[:3000]}"
        )

    return "\n\n".join(sections)


def extract_python_code(response_text: str) -> str:
    python_block = CODE_BLOCK_PATTERN.search(response_text)
    if python_block:
        return python_block.group(1).strip()

    generic_block = GENERIC_CODE_BLOCK_PATTERN.search(response_text)
    if generic_block:
        return generic_block.group(1).strip()

    return response_text.strip()
