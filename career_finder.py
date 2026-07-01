"""
career_finder.py — AI-driven navigation to the Careers/Jobs page.

The CareerFinder uses the AIAgent to reason about each page state and the
BrowserManager to execute the chosen action.  It returns the final URL of the
careers listing page, or None if the page could not be found.
"""

from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse

from loguru import logger

from agent import AIAgent
from browser import BrowserManager

# Keywords that strongly indicate a careers-related URL or link text
_CAREERS_KEYWORDS = re.compile(
    r"\b(career|careers|job|jobs|join[\s-]?us|work[\s-]?with[\s-]?us|"
    r"opportunities|hiring|vacancies|open[\s-]?positions|we.?re[\s-]?hiring|"
    r"employment|team|people|talent|recruit)\b",
    re.IGNORECASE,
)

_MAX_ATTEMPTS = 15  # safety guard against infinite loops


class CareerFinder:
    """
    Navigates from a company homepage to its Careers/Jobs listing page.

    Usage::

        finder = CareerFinder(browser_manager, ai_agent)
        careers_url = await finder.find(company_url)
    """

    def __init__(self, browser: BrowserManager, agent: AIAgent) -> None:
        self._browser = browser
        self._agent = agent

    # ── Public API ────────────────────────────────────────────────────────────

    async def find(self, start_url: str) -> str | None:
        """
        Navigate from *start_url* to the careers page.

        Returns the final URL of the careers page, or None on failure.
        """
        logger.info("Starting career-page search from: {}", start_url)

        # ── Step 1: open the homepage ─────────────────────────────────────
        await self._browser.navigate(start_url)
        logger.info("Opened homepage.")

        # ── Step 2: quick heuristic check before calling the LLM ─────────
        careers_url = await self._heuristic_find(start_url)
        if careers_url:
            logger.info("Heuristic found careers page: {}", careers_url)
            await self._browser.navigate(careers_url)
            return careers_url

        # ── Step 3: LLM-driven navigation loop ───────────────────────────
        for attempt in range(1, _MAX_ATTEMPTS + 1):
            logger.info("Navigation attempt {}/{}", attempt, _MAX_ATTEMPTS)

            page_text = await self._browser.get_page_text()
            elements = await self._browser.get_interactive_elements()
            current_url = await self._browser.get_current_url()

            decision = await self._agent.decide_navigation_action(
                page_text=page_text,
                interactive_elements=elements,
                current_url=current_url,
                attempt=attempt,
            )

            action = decision.get("action", "give_up")
            target = decision.get("target", "")
            reason = decision.get("reason", "")

            logger.info("AI decision — action={} target='{}' reason='{}'", action, target, reason)

            if action == "found":
                logger.success("AI reports careers page found at: {}", current_url)
                return current_url

            elif action == "give_up":
                logger.warning("AI gave up searching for careers page.")
                break

            elif action == "navigate":
                # AI wants to go directly to a URL
                nav_url = self._resolve_url(target, current_url)
                await self._browser.navigate(nav_url)

            elif action == "click_link":
                success = await self._click_text(target)
                if not success:
                    logger.warning("Could not click link: '{}'", target)
                    # Try scrolling to reveal more content and retry
                    await self._browser.scroll_to_bottom()

            elif action == "click_button":
                success = await self._click_text(target)
                if not success:
                    logger.warning("Could not click button: '{}'", target)

            elif action == "scroll":
                await self._browser.scroll_to_bottom()

            else:
                logger.warning("Unknown action from AI: {}", action)

            # After each action, check if we landed on a careers page
            new_url = await self._browser.get_current_url()
            if _CAREERS_KEYWORDS.search(new_url):
                logger.success(
                    "URL indicates careers page after navigation: {}", new_url
                )
                return new_url

        logger.error("Failed to find careers page after {} attempts.", _MAX_ATTEMPTS)
        return None

    # ── Private helpers ───────────────────────────────────────────────────────

    async def _heuristic_find(self, base_url: str) -> str | None:
        """
        Before calling the LLM, scan all links on the current page for obvious
        careers-related URLs or link text.  Returns the best matching URL, or None.
        """
        links = await self._browser.get_all_links()
        scored: list[tuple[int, str]] = []

        for link in links:
            text = link.get("text", "")
            href = link.get("href", "")
            score = 0

            if _CAREERS_KEYWORDS.search(text):
                score += 2
            if _CAREERS_KEYWORDS.search(href):
                score += 1

            if score > 0:
                scored.append((score, href))

        if not scored:
            return None

        # Return the highest-scoring link
        scored.sort(reverse=True)
        return scored[0][1]

    async def _click_text(self, text: str) -> bool:
        """
        Attempt to click an element whose visible text contains *text*.
        Tries exact match first, then partial.
        """
        # Try Playwright's built-in role-based click
        success = await self._browser.click_by_text(text)
        if success:
            return True

        # Fallback: find by partial text in all links
        links = await self._browser.get_all_links()
        for link in links:
            if text.lower() in link.get("text", "").lower():
                href = link.get("href", "")
                if href:
                    await self._browser.navigate(href)
                    return True

        return False

    @staticmethod
    def _resolve_url(target: str, current_url: str) -> str:
        """Turn relative targets into absolute URLs."""
        if target.startswith(("http://", "https://")):
            return target
        base = urlparse(current_url)
        base_url = f"{base.scheme}://{base.netloc}"
        return urljoin(base_url, target)
