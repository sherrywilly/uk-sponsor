"""
browser.py — Playwright browser lifecycle management.

Launches a visible (headed) Chromium browser so the user can always see what
the scraper is doing. Exposes a thin async context-manager API used by the
rest of the application.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, AsyncGenerator, Awaitable, Callable

from dotenv import load_dotenv
from loguru import logger
from playwright.async_api import (
    Browser,
    BrowserContext,
    Page,
    Playwright,
    async_playwright,
)

load_dotenv()

# ── Browser configuration read from environment (with sensible defaults) ─────

_HEADLESS_ENV = os.getenv("HEADLESS")
_HAS_DISPLAY = bool(os.getenv("DISPLAY"))

if _HEADLESS_ENV is None:
    # In containers/CI there is usually no X server, so default to headless.
    HEADLESS: bool = not _HAS_DISPLAY
else:
    HEADLESS = _HEADLESS_ENV.lower() == "true"
    if not _HAS_DISPLAY and not HEADLESS:
        logger.warning(
            "HEADLESS=false requested but no DISPLAY detected; forcing headless mode."
        )
        HEADLESS = True
SLOW_MO: int = int(os.getenv("SLOW_MO", "400"))  # milliseconds between actions
_OUTPUT_DIR = os.getenv("OUTPUT_DIR", "output")
_SCREENSHOT_STEPS: bool = os.getenv("SCREENSHOT_STEPS", "true").lower() == "true"

# A realistic user-agent keeps most sites from blocking the crawler
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


class BrowserManager:
    """Manages the Playwright browser, context, and page lifecycle."""

    def __init__(self) -> None:
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None
        self._step_counter: int = 0
        self._action_listener: Callable[[dict[str, Any]], Awaitable[None] | None] | None = None

    # ── Public properties ────────────────────────────────────────────────────

    @property
    def page(self) -> Page:
        if self._page is None:
            raise RuntimeError("Browser not started. Call start() first.")
        return self._page

    def set_action_listener(
        self,
        listener: Callable[[dict[str, Any]], Awaitable[None] | None] | None,
    ) -> None:
        self._action_listener = listener

    # ── Lifecycle ────────────────────────────────────────────────────────────

    async def start(self) -> "BrowserManager":
        """Launch Chromium and open a new page."""
        logger.info("Launching Chromium (headless={}, slow_mo={}ms)", HEADLESS, SLOW_MO)
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=HEADLESS,
            slow_mo=SLOW_MO,
            args=[
                "--start-maximized",
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-web-security",
            ],
        )
        self._context = await self._browser.new_context(
            user_agent=_USER_AGENT,
            viewport={"width": 1440, "height": 900},
            java_script_enabled=True,
            accept_downloads=False,
            extra_http_headers={
                "Accept-Language": "en-GB,en;q=0.9",
            },
        )
        # Hide navigator.webdriver so JS frameworks don't block headless browsers
        await self._context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )
        # Block images / fonts / media to speed things up while still
        # rendering enough for the AI to read the page content.
        await self._context.route(
            "**/*.{png,jpg,jpeg,gif,webp,svg,woff,woff2,ttf,otf,mp4,mp3,avi}",
            lambda route: route.abort(),
        )
        self._page = await self._context.new_page()
        logger.info("Browser ready.")
        return self

    async def stop(self) -> None:
        """Close page, context, browser, and the Playwright instance."""
        logger.info("Shutting down browser.")
        if self._page and not self._page.is_closed():
            await self._page.close()
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        logger.info("Browser shut down.")

    # ── Helpers ──────────────────────────────────────────────────────────────

    async def navigate(self, url: str, *, wait_until: str = "domcontentloaded") -> None:
        """Navigate to *url* and wait for the page to settle."""
        await self._emit_action("browser.navigate", f"Navigating to {url}")
        logger.info("Navigating to: {}", url)
        await self.page.goto(url, wait_until=wait_until, timeout=60_000)
        await self._wait_for_network_idle()
        await self._wait_for_js_render()
        await self._capture_step_screenshot("navigate")

    async def _wait_for_js_render(self, timeout: int = 15_000) -> None:
        """
        Wait until the page has meaningful visible text — catches JS/React
        frameworks that render content after networkidle fires.
        Requires >1000 chars to avoid being satisfied by loading-screen placeholders.
        """
        try:
            await self.page.wait_for_function(
                "() => (document.body.innerText || '').trim().length > 1000",
                timeout=timeout,
            )
        except Exception:
            # Page may genuinely have little text (e.g. login walls); continue.
            pass

    async def wait_for_selector_any(
        self, selectors: list[str], timeout: int = 20_000
    ) -> bool:
        """
        Wait for the first matching selector to appear on the page.
        Returns True if found, False on timeout.
        Useful for JS-heavy frameworks (Workday, Greenhouse, Lever, etc.).
        """
        import asyncio

        found = asyncio.Event()

        async def _try(sel: str) -> None:
            try:
                await self.page.wait_for_selector(sel, timeout=timeout)
                found.set()
            except Exception:
                pass

        tasks = [asyncio.create_task(_try(sel)) for sel in selectors]
        try:
            await asyncio.wait_for(found.wait(), timeout=timeout / 1000)
            return True
        except asyncio.TimeoutError:
            return False
        finally:
            for t in tasks:
                t.cancel()

    async def scroll_to_bottom(self) -> None:
        """Scroll the page to the bottom to trigger lazy-loaded content."""
        await self._emit_action("browser.scroll", "Scrolling to bottom")
        logger.debug("Scrolling to bottom of page.")
        await self.page.evaluate(
            "window.scrollTo({ top: document.body.scrollHeight, behavior: 'smooth' })"
        )
        await self.page.wait_for_timeout(800)
        await self._capture_step_screenshot("scroll_bottom")

    async def get_page_text(self) -> str:
        """Return the visible text content of the current page."""
        return await self.page.evaluate("() => document.body.innerText")

    async def get_page_html(self) -> str:
        """Return the full outer HTML of the current page."""
        return await self.page.content()

    async def get_current_url(self) -> str:
        return self.page.url

    async def click_element(self, selector: str) -> None:
        """Click a CSS / XPath selector with a short wait before & after."""
        await self._emit_action("browser.click", f"Clicking selector {selector}")
        logger.debug("Clicking element: {}", selector)
        await self.page.wait_for_selector(selector, timeout=10_000)
        await self.page.click(selector)
        await self._wait_for_network_idle()
        await self._capture_step_screenshot("click_selector")

    async def click_by_text(self, text: str) -> bool:
        """
        Try to click the first visible link / button whose text contains *text*.
        Returns True on success, False if nothing was found.
        """
        locator = self.page.get_by_role("link", name=text, exact=False)
        if await locator.count() == 0:
            locator = self.page.get_by_role("button", name=text, exact=False)
        if await locator.count() == 0:
            return False
        await self._emit_action("browser.click", f"Clicking visible text '{text}'")
        await locator.first.click()
        await self._wait_for_network_idle()
        await self._capture_step_screenshot("click_text")
        return True

    async def get_all_links(self) -> list[dict]:
        """Return a list of {text, href} dicts for every <a> on the page."""
        return await self.page.evaluate(
            """() => {
                const links = [];
                document.querySelectorAll('a[href]').forEach(a => {
                    const text = (a.innerText || a.textContent || '').trim();
                    const href = a.href;
                    if (text && href && !href.startsWith('javascript:')) {
                        links.push({ text, href });
                    }
                });
                return links;
            }"""
        )

    async def get_interactive_elements(self) -> list[dict]:
        """
        Return a condensed list of interactive elements (links, buttons, selects)
        that the AI agent can reason about.
        """
        return await self.page.evaluate(
            """() => {
                const items = [];
                const selectors = ['a[href]', 'button', 'select', '[role="button"]', '[role="menuitem"]'];
                selectors.forEach(sel => {
                    document.querySelectorAll(sel).forEach(el => {
                        const rect = el.getBoundingClientRect();
                        // only include elements that are visible in the viewport
                        if (rect.width > 0 && rect.height > 0) {
                            const text = (el.innerText || el.textContent || el.getAttribute('aria-label') || '').trim();
                            const href = el.href || '';
                            if (text) {
                                items.push({ tag: el.tagName.toLowerCase(), text: text.substring(0, 120), href });
                            }
                        }
                    });
                });
                return items;
            }"""
        )

    # ── Private helpers ──────────────────────────────────────────────────────

    async def _wait_for_network_idle(self, timeout: int = 8_000) -> None:
        """Wait up to *timeout* ms for network to go quiet."""
        try:
            await self.page.wait_for_load_state("networkidle", timeout=timeout)
        except Exception:
            # networkidle can time-out on pages with long-polling – that's fine.
            pass

    async def _capture_step_screenshot(self, label: str) -> None:
        """Capture a screenshot for each browser action step when enabled."""
        if not _SCREENSHOT_STEPS:
            return
        try:
            shots_dir = Path(_OUTPUT_DIR) / "screenshots" / "steps"
            shots_dir.mkdir(parents=True, exist_ok=True)
            self._step_counter += 1
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"step_{self._step_counter:04d}_{label}_{ts}.png"
            await self.page.screenshot(path=str(shots_dir / filename), full_page=False)
        except Exception as exc:
            logger.debug("Step screenshot skipped: {}", exc)

    async def _emit_action(self, action: str, details: str) -> None:
        if self._action_listener is None:
            return
        result = self._action_listener({"action": action, "details": details})
        if result is not None:
            await result


# ── Convenience async context manager ────────────────────────────────────────


@asynccontextmanager
async def browser_session() -> AsyncGenerator[BrowserManager, None]:
    """
    Async context manager that starts and stops a BrowserManager.

    Usage::

        async with browser_session() as bm:
            await bm.navigate("https://example.com")
    """
    manager = BrowserManager()
    await manager.start()
    try:
        yield manager
    finally:
        await manager.stop()
