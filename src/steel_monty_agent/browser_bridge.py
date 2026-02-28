from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .steel_sdk import SessionInfo, SteelSDKBrowser


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


_ACTIVE_BRIDGES: dict[int, "BrowserBridge"] = {}


def _register_bridge(bridge: "BrowserBridge") -> int:
    bridge_id = id(bridge)
    _ACTIVE_BRIDGES[bridge_id] = bridge
    return bridge_id


def _unregister_bridge(bridge_id: int) -> None:
    _ACTIVE_BRIDGES.pop(bridge_id, None)


def _get_bridge(bridge_id: int) -> "BrowserBridge":
    bridge = _ACTIVE_BRIDGES.get(bridge_id)
    if bridge is None:
        raise RuntimeError("Browser handle is no longer active.")
    return bridge


@dataclass
class BridgeEvent:
    ts: str
    action: str
    args: dict[str, Any]
    result_preview: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Locator:
    bridge_id: int
    selector: str

    def click(self) -> dict[str, Any]:
        return _get_bridge(self.bridge_id).click(self.selector)

    def fill(self, value: str) -> dict[str, Any]:
        return _get_bridge(self.bridge_id).fill(self.selector, value)

    def text(self) -> str:
        return _get_bridge(self.bridge_id).get_text(self.selector)

    def attr(self, attr: str) -> str:
        return _get_bridge(self.bridge_id).get_attr(self.selector, attr)

    def wait_visible(self) -> dict[str, Any]:
        return _get_bridge(self.bridge_id).wait_for(selector=self.selector)


@dataclass
class Page:
    bridge_id: int

    def goto(self, url: str) -> None:
        _get_bridge(self.bridge_id).open_url(url)

    def url(self) -> str:
        return _get_bridge(self.bridge_id).get_url()

    def title(self) -> str:
        return _get_bridge(self.bridge_id).get_title()

    def snapshot(self, interactive: bool = True) -> str:
        return _get_bridge(self.bridge_id).snapshot(interactive=interactive)

    def locator(self, selector: str) -> Locator:
        return Locator(bridge_id=self.bridge_id, selector=selector)

    def click(self, selector: str) -> dict[str, Any]:
        return _get_bridge(self.bridge_id).click(selector)

    def fill(self, selector: str, value: str) -> dict[str, Any]:
        return _get_bridge(self.bridge_id).fill(selector, value)

    def text(self, selector: str) -> str:
        return _get_bridge(self.bridge_id).get_text(selector)

    def attr(self, selector: str, attr: str) -> str:
        return _get_bridge(self.bridge_id).get_attr(selector, attr)

    def wait_for_text(self, text: str) -> dict[str, Any]:
        return _get_bridge(self.bridge_id).wait_for(text=text)

    def wait_for_selector(self, selector: str) -> dict[str, Any]:
        return _get_bridge(self.bridge_id).wait_for(selector=selector)

    def wait_for_ms(self, ms: int) -> dict[str, Any]:
        return _get_bridge(self.bridge_id).wait_for(ms=ms)

    def eval_js(self, script: str) -> str:
        return _get_bridge(self.bridge_id).eval_js(script)

    def screenshot(self, path: str | None = None) -> str:
        return _get_bridge(self.bridge_id).screenshot(path=path)


@dataclass
class Browser:
    bridge_id: int
    session_id: str
    mode: str
    name: str | None = None
    connect_url: str | None = None
    live_url: str | None = None

    def open_page(self, url: str) -> Page:
        _get_bridge(self.bridge_id).open_url(url)
        return Page(bridge_id=self.bridge_id)

    def current_page(self) -> Page:
        return Page(bridge_id=self.bridge_id)

    def close(self) -> dict[str, Any]:
        return _get_bridge(self.bridge_id).stop_browser()


@dataclass
class BrowserBridge:
    backend: SteelSDKBrowser
    run_dir: Path
    _events: list[BridgeEvent] = field(default_factory=list)
    _final_result: dict[str, Any] | None = None
    _session_started: bool = False
    _snapshot_counter: int = 0
    _screenshot_counter: int = 0
    _last_observation: str | None = None

    def __post_init__(self) -> None:
        self.run_dir.mkdir(parents=True, exist_ok=True)

    @property
    def final_result(self) -> dict[str, Any] | None:
        return self._final_result

    @staticmethod
    def normalize_result_payload(payload: Any) -> dict[str, Any]:
        if isinstance(payload, dict):
            normalized: dict[str, Any] = dict(payload)
        else:
            normalized = {"results": payload}

        status = normalized.get("status")
        normalized["status"] = status if isinstance(status, str) and status else "ok"

        if "results" not in normalized:
            normalized["results"] = []

        evidence = normalized.get("evidence")
        if isinstance(evidence, list):
            normalized["evidence"] = [str(item) for item in evidence]
        else:
            normalized["evidence"] = []

        errors = normalized.get("errors")
        if isinstance(errors, list):
            normalized["errors"] = [str(item) for item in errors]
        else:
            normalized["errors"] = []

        artifacts = normalized.get("artifacts")
        if not isinstance(artifacts, dict):
            artifacts = {}
        normalized["artifacts"] = artifacts

        return normalized

    def _record(self, action: str, args: dict[str, Any], result_preview: str | None = None) -> None:
        self._events.append(
            BridgeEvent(
                ts=_utc_now_iso(),
                action=action,
                args=args,
                result_preview=result_preview[:800] if result_preview else None,
            )
        )

    def last_observation(self) -> str | None:
        return self._last_observation

    def start_browser(
        self,
        session_name: str | None = None,
        local: bool | None = None,
        api_url: str | None = None,
    ) -> Browser:
        print("Starting Steel session...", flush=True)
        started = time.perf_counter()
        if session_name is not None:
            self.backend.session_name = session_name
        if local is not None and local != self.backend.local:
            self.backend.local = local
        if api_url is not None:
            self.backend.api_url = api_url or None

        info: SessionInfo = self.backend.start_session()
        elapsed = time.perf_counter() - started
        print(f"Steel session ready in {elapsed:.2f}s (id: {info.id})", flush=True)
        self._session_started = True

        bridge_id = _register_bridge(self)
        payload = asdict(info)
        self._record(
            "start_browser",
            {"session_name": self.backend.session_name, "bridge_id": bridge_id},
            json.dumps(payload),
        )
        return Browser(
            bridge_id=bridge_id,
            session_id=info.id,
            mode=info.mode,
            name=info.name,
            connect_url=info.connect_url,
            live_url=info.live_url,
        )

    def stop_browser(self) -> dict[str, Any]:
        _unregister_bridge(id(self))
        if not self._session_started:
            self._record("stop_browser", {"skipped": True}, "session_not_started")
            return {"ok": True, "stopped": False}

        output = self.backend.stop_session(all_sessions=False)
        self._session_started = False
        self._record("stop_browser", {"skipped": False}, output)
        return {"ok": True, "stopped": True, "output": output}

    def stop_session(self) -> dict[str, Any]:
        return self.stop_browser()

    def open_url(self, url: str) -> dict[str, Any]:
        output = self.backend.open_url(url)
        self._record("open_url", {"url": url}, output)
        return self.backend.ok_payload("open_url", output)

    def snapshot(self, interactive: bool = True) -> str:
        output = self.backend.snapshot(interactive=interactive)
        self._snapshot_counter += 1
        snapshot_path = self.run_dir / f"snapshot_{self._snapshot_counter:02d}.txt"
        snapshot_path.write_text(output, encoding="utf-8")
        self._last_observation = output[:3000]
        self._record(
            "snapshot",
            {"interactive": interactive, "path": str(snapshot_path)},
            output,
        )
        return output

    def click(self, target: str) -> dict[str, Any]:
        output = self.backend.click(target)
        self._record("click", {"target": target}, output)
        return self.backend.ok_payload("click", output)

    def fill(self, target: str, value: str) -> dict[str, Any]:
        output = self.backend.fill(target, value)
        self._record("fill", {"target": target, "value": value}, output)
        return self.backend.ok_payload("fill", output)

    def wait_for(
        self,
        text: str | None = None,
        selector: str | None = None,
        ms: int | None = None,
    ) -> dict[str, Any]:
        output = self.backend.wait_for(text=text, selector=selector, ms=ms)
        self._record("wait_for", {"text": text, "selector": selector, "ms": ms}, output)
        return self.backend.ok_payload("wait_for", output)

    def get_text(self, target: str) -> str:
        output = self.backend.get_text(target)
        self._record("get_text", {"target": target}, output)
        return output

    def get_attr(self, target: str, attr: str) -> str:
        output = self.backend.get_attr(target, attr)
        self._record("get_attr", {"target": target, "attr": attr}, output)
        return output

    def get_url(self) -> str:
        output = self.backend.get_url()
        self._record("get_url", {}, output)
        return output

    def get_title(self) -> str:
        output = self.backend.get_title()
        self._record("get_title", {}, output)
        return output

    def eval_js(self, script: str) -> str:
        output = self.backend.eval_js(script)
        self._record("eval_js", {"script": script}, output)
        return output

    def screenshot(self, path: str | None = None) -> str:
        if path:
            screenshot_path = Path(path)
            if not screenshot_path.is_absolute():
                screenshot_path = self.run_dir / screenshot_path
        else:
            self._screenshot_counter += 1
            screenshot_path = self.run_dir / f"screenshot_{self._screenshot_counter:02d}.png"

        output = self.backend.screenshot(str(screenshot_path))
        self._record("screenshot", {"path": str(screenshot_path)}, output)
        return str(screenshot_path)

    def emit_result(self, payload: Any) -> dict[str, Any]:
        normalized = self.normalize_result_payload(payload)
        self._final_result = normalized
        self._record("emit_result", {"keys": sorted(normalized.keys())}, "result_emitted")
        return normalized

    def external_functions(self) -> dict[str, Any]:
        return {
            "start_browser": self.start_browser,
            "emit_result": self.emit_result,
        }

    def dump_events(self, path: Path) -> None:
        serializable = [event.to_dict() for event in self._events]
        path.write_text(json.dumps(serializable, indent=2, ensure_ascii=True), encoding="utf-8")
