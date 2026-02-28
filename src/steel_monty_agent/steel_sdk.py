from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse


class SteelSDKError(RuntimeError):
    pass


@dataclass
class SessionInfo:
    id: str
    mode: str
    name: str | None
    connect_url: str | None
    live_url: str | None


@dataclass
class SteelSDKBrowser:
    session_name: str
    steel_api_key: str | None = None
    local: bool = False
    api_url: str | None = None
    timeout_sec: int = 30

    def __post_init__(self) -> None:
        self._steel_client: Any | None = None
        self._playwright: Any | None = None
        self._browser: Any | None = None
        self._context: Any | None = None
        self._page: Any | None = None
        self._session: Any | None = None
        self._element_refs: dict[str, Any] = {}

    def _resolve_base_url(self) -> str | None:
        if self.api_url:
            return self.api_url
        if self.local:
            return (
                os.getenv("STEEL_BROWSER_API_URL")
                or os.getenv("STEEL_LOCAL_API_URL")
                or "http://localhost:3000/v1"
            )
        return None

    def _resolve_api_key(self) -> str | None:
        if self.steel_api_key and self.steel_api_key.strip():
            return self.steel_api_key.strip()
        env_key = os.getenv("STEEL_API_KEY", "").strip()
        return env_key or None

    def _ensure_connect_url(self, websocket_url: str, session_id: str) -> str:
        parsed = urlparse(websocket_url)
        query = parse_qs(parsed.query, keep_blank_values=True)
        is_cloud_connect_host = "connect.steel.dev" in (parsed.netloc or "")

        changed = False
        if is_cloud_connect_host and not query.get("sessionId"):
            query["sessionId"] = [session_id]
            changed = True

        if is_cloud_connect_host and not query.get("apiKey"):
            api_key = self._resolve_api_key()
            if not api_key:
                raise SteelSDKError(
                    "Missing STEEL_API_KEY for CDP connect URL construction."
                )
            query["apiKey"] = [api_key]
            changed = True

        if not changed:
            return websocket_url

        rebuilt = parsed._replace(query=urlencode(query, doseq=True))
        return urlunparse(rebuilt)

    def _client(self) -> Any:
        if self._steel_client is not None:
            return self._steel_client

        try:
            from steel import Steel
        except ImportError as exc:
            raise SteelSDKError(
                "Missing steel-sdk package. Install dependencies with `uv sync`."
            ) from exc

        kwargs: dict[str, Any] = {}
        if self.steel_api_key:
            kwargs["steel_api_key"] = self.steel_api_key

        base_url = self._resolve_base_url()
        if base_url:
            kwargs["base_url"] = base_url

        self._steel_client = Steel(**kwargs)
        return self._steel_client

    def _require_page(self) -> Any:
        if self._page is None:
            raise SteelSDKError("Browser page is not initialized. Call start_session() first.")
        return self._page

    @staticmethod
    def _looks_like_host_without_protocol(url: str) -> bool:
        host_candidate = (url.split("/", 1)[0] or "").lower()
        return (
            host_candidate == "localhost"
            or host_candidate.startswith("localhost:")
            or bool(re.match(r"^\d{1,3}(?:\.\d{1,3}){3}(?::\d+)?$", host_candidate))
            or "." in host_candidate
        )

    def _normalize_url(self, url: str) -> str:
        candidate = (url or "").strip()
        if not candidate:
            raise SteelSDKError("open_url requires a non-empty URL.")
        lowered = candidate.lower()
        if "://" in lowered or lowered.startswith(("about:", "data:", "file:", "blob:", "javascript:")):
            return candidate
        if self._looks_like_host_without_protocol(candidate):
            return f"https://{candidate}"
        return candidate

    def start_session(self) -> SessionInfo:
        if self._session is not None and self._page is not None:
            return SessionInfo(
                id=str(getattr(self._session, "id", "") or ""),
                mode="local" if self.local else "cloud",
                name=self.session_name or None,
                connect_url=getattr(self._session, "websocket_url", None),
                live_url=getattr(self._session, "session_viewer_url", None),
            )

        client = self._client()

        create_kwargs: dict[str, Any] = {}
        if self.session_name:
            create_kwargs["namespace"] = self.session_name

        session = client.sessions.create(**create_kwargs)
        session_id = str(getattr(session, "id", "") or "")
        if not session_id:
            raise SteelSDKError("Session did not return id.")

        websocket_url = getattr(session, "websocket_url", None)
        if not websocket_url:
            raise SteelSDKError("Session did not return websocket_url.")
        websocket_url = self._ensure_connect_url(str(websocket_url), session_id)

        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise SteelSDKError(
                "Missing playwright package. Install dependencies with `uv sync`."
            ) from exc

        try:
            self._playwright = sync_playwright().start()
            self._browser = self._playwright.chromium.connect_over_cdp(
                websocket_url,
                timeout=self.timeout_sec * 1000,
            )
            if self._browser.contexts:
                self._context = self._browser.contexts[0]
            else:
                self._context = self._browser.new_context()

            if self._context.pages:
                self._page = self._context.pages[0]
            else:
                self._page = self._context.new_page()

            self._page.set_default_timeout(self.timeout_sec * 1000)
            self._session = session
        except Exception as exc:
            if self._browser is not None:
                try:
                    self._browser.close()
                except Exception:
                    pass
            if self._playwright is not None:
                try:
                    self._playwright.stop()
                except Exception:
                    pass
            try:
                client.sessions.release(session_id)
            except Exception:
                pass
            self._playwright = None
            self._browser = None
            self._context = None
            self._page = None
            self._session = None
            raise SteelSDKError(f"Failed to attach to Steel session CDP: {exc}") from exc

        return SessionInfo(
            id=session_id,
            mode="local" if self.local else "cloud",
            name=self.session_name or None,
            connect_url=websocket_url,
            live_url=getattr(session, "session_viewer_url", None),
        )

    def stop_session(self, all_sessions: bool = False) -> str:
        _ = all_sessions
        errors: list[str] = []
        session_id = str(getattr(self._session, "id", "") or "")

        if self._browser is not None:
            try:
                self._browser.close()
            except Exception as exc:
                errors.append(f"browser.close failed: {exc}")
        if self._playwright is not None:
            try:
                self._playwright.stop()
            except Exception as exc:
                errors.append(f"playwright.stop failed: {exc}")

        if session_id:
            try:
                self._client().sessions.release(session_id)
            except Exception as exc:
                errors.append(f"sessions.release failed: {exc}")

        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None
        self._session = None
        self._element_refs = {}

        if errors:
            raise SteelSDKError("; ".join(errors))
        return "session stopped"

    def open_url(self, url: str) -> str:
        page = self._require_page()
        normalized_url = self._normalize_url(url)
        page.goto(normalized_url, wait_until="domcontentloaded")
        return f"opened {normalized_url}"

    def snapshot(self, interactive: bool = True) -> str:
        _ = interactive
        page = self._require_page()

        lines: list[str] = [
            f"URL: {page.url}",
            f"Title: {page.title()}",
            "Elements:",
        ]

        elements = page.query_selector_all("a,button,input,select,textarea,[role='button']")
        self._element_refs = {}

        for idx, element in enumerate(elements[:100], start=1):
            ref = f"@e{idx}"
            self._element_refs[ref] = element

            try:
                tag = element.evaluate("el => el.tagName.toLowerCase()")
            except Exception:
                tag = "unknown"
            try:
                text = (element.inner_text() or "").strip().replace("\n", " ")
            except Exception:
                text = ""
            if len(text) > 120:
                text = text[:117] + "..."

            attrs: list[str] = []
            for attr_name in ("id", "name", "placeholder", "aria-label"):
                try:
                    attr_value = element.get_attribute(attr_name)
                except Exception:
                    attr_value = None
                if attr_value:
                    attrs.append(f'{attr_name}="{attr_value}"')

            attrs_blob = " ".join(attrs).strip()
            if attrs_blob:
                lines.append(f'{ref} <{tag}> text="{text}" {attrs_blob}')
            else:
                lines.append(f'{ref} <{tag}> text="{text}"')

        return "\n".join(lines)

    def _resolve_target(self, target: str) -> tuple[Any | None, Any | None]:
        if not target or not target.strip():
            raise SteelSDKError("Target must not be empty.")
        page = self._require_page()
        if target in self._element_refs:
            return self._element_refs[target], None
        return None, page.locator(target).first

    def click(self, target: str) -> str:
        element, locator = self._resolve_target(target)
        if element is not None:
            element.click(timeout=self.timeout_sec * 1000)
        else:
            locator.click(timeout=self.timeout_sec * 1000)
        return f"clicked {target}"

    def fill(self, target: str, value: str) -> str:
        element, locator = self._resolve_target(target)
        if element is not None:
            element.fill(value, timeout=self.timeout_sec * 1000)
        else:
            locator.fill(value, timeout=self.timeout_sec * 1000)
        return f"filled {target}"

    def wait_for(
        self,
        *,
        text: str | None = None,
        selector: str | None = None,
        ms: int | None = None,
    ) -> str:
        page = self._require_page()
        if ms is not None:
            if ms <= 0:
                raise SteelSDKError("wait_for ms must be > 0.")
            page.wait_for_timeout(ms)
            return f"waited {ms}ms"
        if text:
            page.get_by_text(text).first.wait_for(state="visible", timeout=self.timeout_sec * 1000)
            return f'waited for text "{text}"'
        if selector:
            page.locator(selector).first.wait_for(state="visible", timeout=self.timeout_sec * 1000)
            return f'waited for selector "{selector}"'
        raise SteelSDKError("wait_for requires one of: text, selector, ms.")

    def get_text(self, target: str) -> str:
        element, locator = self._resolve_target(target)
        if element is not None:
            return (element.inner_text() or "").strip()
        return (locator.inner_text() or "").strip()

    def get_attr(self, target: str, attr: str) -> str:
        element, locator = self._resolve_target(target)
        value = element.get_attribute(attr) if element is not None else locator.get_attribute(attr)
        return value or ""

    def get_url(self) -> str:
        return self._require_page().url

    def get_title(self) -> str:
        return self._require_page().title()

    def eval_js(self, script: str) -> str:
        result = self._require_page().evaluate(script)
        if isinstance(result, str):
            return result
        return json.dumps(result, ensure_ascii=True, default=str)

    def screenshot(self, path: str) -> str:
        screenshot_path = Path(path)
        screenshot_path.parent.mkdir(parents=True, exist_ok=True)
        self._require_page().screenshot(path=str(screenshot_path), full_page=True)
        return str(screenshot_path)

    @staticmethod
    def ok_payload(action: str, output: str) -> dict[str, Any]:
        return {"ok": True, "action": action, "output": output}
