"""
browser.py — Playwright browser lifecycle management.

Launches a visible (headed) Chromium browser so the user can always see what
the scraper is doing. Exposes a thin async context-manager API used by the
rest of the application.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

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

HEADLESS: bool = os.getenv("HEADLESS", "false").lower() == "true"
SLOW_MO: int = int(os.getenv("SLOW_MO", "400"))  # milliseconds between actions

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

    # ── Public properties ────────────────────────────────────────────────────

    @property
    def page(self) -> Page:
        if self._page is None:
            raise RuntimeError("Browser not started. Call start() first.")
        return self._page

    # ── Lifecycle ────────────────────────────────────────────────────────────

    async def start(self) -> "BrowserManager":
        """Launch Chromium and open a new page."""
        logger.info("Launching Chromium (headless={}, slow_mo={}ms)", HEADLESS, SLOW_MO)
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=HEADLESS,
            slow_mo=SLOW_MO,
            args=["--start-maximized"],
        )
        self._context = await self._browser.new_context(
            user_agent=_USER_AGENT,
            viewport={"width": 1440, "height": 900},
            java_script_enabled=True,
            accept_downloads=False,
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
        logger.info("Navigating to: {}", url)
        await self.page.goto(url, wait_until=wait_until, timeout=60_000)
        await self._wait_for_network_idle()

    async def scroll_to_bottom(self) -> None:
        """Scroll the page to the bottom to trigger lazy-loaded content."""
        logger.debug("Scrolling to bottom of page.")
        await self.page.evaluate(
            "window.scrollTo({ top: document.body.scrollHeight, behavior: 'smooth' })"
        )
        await self.page.wait_for_timeout(800)

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
        logger.debug("Clicking element: {}", selector)
        await self.page.wait_for_selector(selector, timeout=10_000)
        await self.page.click(selector)
        await self._wait_for_network_idle()

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
        await locator.first.click()
        await self._wait_for_network_idle()
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
