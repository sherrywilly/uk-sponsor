"""
tools.py — Browser tool definitions and executor.

Every tool the LLM is allowed to call is defined here.  The LLM never touches
Playwright directly; it only names a tool and provides arguments.  The
ToolExecutor receives that decision and runs the matching Playwright operation.

Tool catalogue
--------------
goto(url)                Navigate to a URL.
click(selector)          Click an element by CSS selector or visible text.
type(selector, text)     Type text into an input field.
scroll(direction)        Scroll "down", "up", or "bottom".
wait(ms)                 Wait for a number of milliseconds (max 5 000).
screenshot(filename)     Take a screenshot and save it to output/screenshots/.
extract_text()           Return the visible text of the current page.
extract_links()          Return all visible links {text, href} on the page.
current_url()            Return the current page URL.
page_title()             Return the current page <title>.
save_csv(rows, filename) Serialise a list-of-dicts to output/<filename>.csv.
dismiss_popup()          Try to close cookie banners / modals / overlays.
"""

from __future__ import annotations

import csv
import os
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from loguru import logger

from browser import BrowserManager

_OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", "output"))
_SCREENSHOTS_DIR = _OUTPUT_DIR / "screenshots"


class Tool(str, Enum):
    GOTO = "goto"
    CLICK = "click"
    TYPE = "type"
    SCROLL = "scroll"
    WAIT = "wait"
    SCREENSHOT = "screenshot"
    EXTRACT_TEXT = "extract_text"
    EXTRACT_LINKS = "extract_links"
    CURRENT_URL = "current_url"
    PAGE_TITLE = "page_title"
    SAVE_CSV = "save_csv"
    DISMISS_POPUP = "dismiss_popup"
    DONE = "done"          # signals the agent that the task is complete
    GIVE_UP = "give_up"   # signals the agent that it cannot complete the task


# Human-readable descriptions injected into the system prompt
TOOL_DESCRIPTIONS: dict[str, str] = {
    Tool.GOTO: 'goto(url: str) — Navigate the browser to the given URL.',
    Tool.CLICK: (
        'click(selector: str) — Click an element. '
        'selector can be a CSS selector, an XPath expression, or a visible-text '
        'substring (e.g. "Accept cookies", "Next page").'
    ),
    Tool.TYPE: (
        'type(selector: str, text: str) — Click the element matching selector '
        'then type text into it.'
    ),
    Tool.SCROLL: (
        'scroll(direction: str) — Scroll the page. '
        'direction must be one of: "down", "up", "bottom".'
    ),
    Tool.WAIT: 'wait(ms: int) — Pause execution for ms milliseconds (max 5000).',
    Tool.SCREENSHOT: (
        'screenshot(filename: str = "") — Take a screenshot. '
        'filename is optional; a timestamped name is used if omitted.'
    ),
    Tool.EXTRACT_TEXT: 'extract_text() — Return the full visible text of the current page.',
    Tool.EXTRACT_LINKS: (
        'extract_links() — Return all visible hyperlinks on the current page '
        'as a list of {text, href} objects.'
    ),
    Tool.CURRENT_URL: 'current_url() — Return the URL of the current page.',
    Tool.PAGE_TITLE: 'page_title() — Return the <title> of the current page.',
    Tool.SAVE_CSV: (
        'save_csv(rows: list[dict], filename: str) — '
        'Write rows (a list of flat dicts) to output/<filename>.'
    ),
    Tool.DISMISS_POPUP: (
        'dismiss_popup() — Attempt to close any visible cookie banner, modal, '
        'or overlay by clicking common dismiss buttons.'
    ),
    Tool.DONE: 'done(result: any) — Signal that the task is complete. Pass the final result.',
    Tool.GIVE_UP: 'give_up(reason: str) — Signal that the task cannot be completed.',
}

# ── Common selectors for cookie/popup dismissal ───────────────────────────────
_DISMISS_TEXTS = [
    "Accept", "Accept all", "Accept cookies", "I accept", "Got it",
    "OK", "Okay", "Agree", "Allow", "Allow all", "Close", "Dismiss",
    "No thanks", "Continue", "I understand",
]
_DISMISS_SELECTORS = [
    "[aria-label*='cookie' i]",
    "[aria-label*='consent' i]",
    "[class*='cookie' i] button",
    "[class*='consent' i] button",
    "[class*='banner' i] button",
    "[id*='cookie' i] button",
    "[id*='consent' i] button",
    "[id*='onetrust-accept' i]",
    "[id*='accept' i]",
    ".cc-btn.cc-allow",
    "#cookieAccept",
]


class ToolResult:
    """Wraps the outcome of executing a tool."""

    def __init__(
        self,
        tool: str,
        args: dict,
        success: bool,
        output: Any = None,
        error: str = "",
    ) -> None:
        self.tool = tool
        self.args = args
        self.success = success
        self.output = output
        self.error = error

    def to_dict(self) -> dict:
        return {
            "tool": self.tool,
            "args": self.args,
            "success": self.success,
            "output": self.output if not isinstance(self.output, (list, dict)) else self.output,
            "error": self.error,
        }

    def __repr__(self) -> str:
        status = "OK" if self.success else f"ERR({self.error})"
        return f"<ToolResult {self.tool} {status}>"


class ToolExecutor:
    """
    Executes tool calls on behalf of the LLM agent.

    The agent supplies a tool name and a dict of arguments; the executor
    maps that to the appropriate BrowserManager (or file-system) operation.
    """

    def __init__(self, browser: BrowserManager) -> None:
        self._browser = browser

    async def execute(self, tool: str, args: dict) -> ToolResult:
        """Dispatch to the correct handler and return a ToolResult."""
        logger.info("Tool call: {}({})", tool, _fmt_args(args))
        try:
            result = await self._dispatch(tool, args)
            return ToolResult(tool=tool, args=args, success=True, output=result)
        except Exception as exc:
            logger.error("Tool {} failed: {}", tool, exc)
            # Take an automatic screenshot on failure for debugging
            await self._auto_screenshot(f"error_{tool}")
            return ToolResult(tool=tool, args=args, success=False, error=str(exc))

    # ── Dispatcher ────────────────────────────────────────────────────────────

    async def _dispatch(self, tool: str, args: dict) -> Any:
        bm = self._browser

        if tool == Tool.GOTO:
            url = str(args.get("url", ""))
            await bm.navigate(url)
            return f"Navigated to {url}"

        elif tool == Tool.CLICK:
            selector = str(args.get("selector", ""))
            # Try role-based text click first (most robust)
            if not selector.startswith((".", "#", "[", "//", "xpath=")):
                success = await bm.click_by_text(selector)
                if success:
                    return f"Clicked by text: '{selector}'"
            # Fall back to CSS/XPath selector
            await bm.click_element(selector)
            return f"Clicked: {selector}"

        elif tool == Tool.TYPE:
            selector = str(args.get("selector", ""))
            text = str(args.get("text", ""))
            await bm.page.click(selector, timeout=10_000)
            await bm.page.fill(selector, text)
            await bm._wait_for_network_idle()
            return f"Typed '{text}' into {selector}"

        elif tool == Tool.SCROLL:
            direction = str(args.get("direction", "down")).lower()
            if direction == "bottom":
                await bm.scroll_to_bottom()
                return "Scrolled to bottom"
            elif direction == "up":
                await bm.page.evaluate(
                    "window.scrollTo({ top: 0, behavior: 'smooth' })"
                )
                await bm.page.wait_for_timeout(600)
                return "Scrolled to top"
            else:  # down
                await bm.page.evaluate(
                    "window.scrollBy({ top: window.innerHeight * 0.8, behavior: 'smooth' })"
                )
                await bm.page.wait_for_timeout(600)
                return "Scrolled down"

        elif tool == Tool.WAIT:
            ms = min(int(args.get("ms", 1000)), 5000)
            await bm.page.wait_for_timeout(ms)
            return f"Waited {ms}ms"

        elif tool == Tool.SCREENSHOT:
            filename = str(args.get("filename", ""))
            path = await self._take_screenshot(filename)
            return str(path)

        elif tool == Tool.EXTRACT_TEXT:
            return await bm.get_page_text()

        elif tool == Tool.EXTRACT_LINKS:
            return await bm.get_all_links()

        elif tool == Tool.CURRENT_URL:
            return await bm.get_current_url()

        elif tool == Tool.PAGE_TITLE:
            return await bm.page.title()

        elif tool == Tool.SAVE_CSV:
            rows = args.get("rows", [])
            filename = str(args.get("filename", "output.csv"))
            return self._save_csv(rows, filename)

        elif tool == Tool.DISMISS_POPUP:
            return await self._dismiss_popup()

        elif tool in (Tool.DONE, Tool.GIVE_UP):
            # Terminal signals — handled by the agent loop, not here
            return args.get("result") or args.get("reason") or ""

        else:
            raise ValueError(f"Unknown tool: {tool!r}")

    # ── Helpers ───────────────────────────────────────────────────────────────

    async def _take_screenshot(self, filename: str = "") -> Path:
        _SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
        if not filename:
            filename = f"screenshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        if not filename.endswith(".png"):
            filename += ".png"
        path = _SCREENSHOTS_DIR / filename
        await self._browser.page.screenshot(path=str(path), full_page=False)
        logger.info("Screenshot saved: {}", path)
        return path

    async def _auto_screenshot(self, label: str) -> None:
        try:
            await self._take_screenshot(
                f"auto_{label}_{datetime.now().strftime('%H%M%S')}"
            )
        except Exception:
            pass

    async def _dismiss_popup(self) -> str:
        """Attempt to dismiss cookie banners and modal overlays."""
        bm = self._browser

        # Try text-based click on common dismiss phrases
        for text in _DISMISS_TEXTS:
            try:
                success = await bm.click_by_text(text)
                if success:
                    logger.info("Dismissed popup by clicking '{}'", text)
                    return f"Dismissed popup: clicked '{text}'"
            except Exception:
                continue

        # Try common CSS selectors
        for sel in _DISMISS_SELECTORS:
            try:
                el = bm.page.locator(sel).first
                if await el.count() > 0 and await el.is_visible():
                    await el.click()
                    await bm._wait_for_network_idle()
                    logger.info("Dismissed popup via selector: {}", sel)
                    return f"Dismissed popup via: {sel}"
            except Exception:
                continue

        return "No dismissible popup found"

    @staticmethod
    def _save_csv(rows: list[dict], filename: str) -> str:
        if not rows:
            return "No rows to save"
        _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        path = _OUTPUT_DIR / filename
        fieldnames = list(rows[0].keys())
        with path.open("w", newline="", encoding="utf-8-sig") as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
        logger.success("Saved {} rows to {}", len(rows), path)
        return str(path)


def _fmt_args(args: dict) -> str:
    """Compact one-line representation of tool arguments for logging."""
    parts = []
    for k, v in args.items():
        if isinstance(v, str) and len(v) > 60:
            v = v[:60] + "…"
        elif isinstance(v, list):
            v = f"[{len(v)} items]"
        parts.append(f"{k}={v!r}")
    return ", ".join(parts)


def tool_catalogue_text() -> str:
    """Return the full tool catalogue as a formatted string for the system prompt."""
    lines = ["Available tools:"]
    for tool, desc in TOOL_DESCRIPTIONS.items():
        lines.append(f"  • {desc}")
    return "\n".join(lines)
