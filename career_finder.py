"""
career_finder.py — AI-driven navigation to the Careers/Jobs page.

Phase 2: CareerFinder now delegates all browser driving to BrowserAgent.
It builds a task description, runs the agent, and returns the final
careers-page URL discovered by the agent.

A lightweight heuristic pre-scan still runs first to avoid an LLM call
when the answer is obvious from the page links.
"""

from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse

from loguru import logger

from agent import AIAgent
from browser import BrowserManager
from browser_agent import BrowserAgent

# Keywords that strongly indicate a careers-related URL or link text
_CAREERS_KEYWORDS = re.compile(
    r"\b(career|careers|job|jobs|join[\s-]?us|work[\s-]?with[\s-]?us|"
    r"opportunities|hiring|vacancies|open[\s-]?positions|we.?re[\s-]?hiring|"
    r"employment|team|people|talent|recruit)\b",
    re.IGNORECASE,
)


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
        self._browser_agent = BrowserAgent(browser=browser, agent=agent, max_iterations=20)

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
        careers_url = await self._heuristic_find()
        if careers_url:
            logger.info("Heuristic found careers page: {}", careers_url)
            await self._browser.navigate(careers_url)
            return careers_url

        # ── Step 3: delegate to BrowserAgent ─────────────────────────────
        task = (
            f"Navigate to the Careers or Jobs page of the company at {start_url}. "
            "The page may be labelled: Careers, Jobs, Join Us, Work With Us, "
            "Opportunities, Hiring, Vacancies, Open Positions, We're Hiring. "
            "Once you are on the careers listing page, call done(result=<current_url>)."
        )
        result = await self._browser_agent.run(task)

        if result:
            final_url = str(result)
            logger.success("BrowserAgent found careers page: {}", final_url)
            # Make sure the browser is on that page
            if await self._browser.get_current_url() != final_url:
                try:
                    await self._browser.navigate(final_url)
                except Exception:
                    pass
            return final_url

        # ── Step 4: last resort — check where the browser ended up ────────
        final_url = await self._browser.get_current_url()
        if _CAREERS_KEYWORDS.search(final_url):
            logger.info("Browser is on a careers URL: {}", final_url)
            return final_url

        logger.error("Could not locate careers page for: {}", start_url)
        return None

    # ── Private helpers ───────────────────────────────────────────────────────

    async def _heuristic_find(self) -> str | None:
        """
        Scan all links on the current page for obvious careers-related URLs or
        link text.  Returns the best matching URL, or None.
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

        scored.sort(reverse=True)
        return scored[0][1]
