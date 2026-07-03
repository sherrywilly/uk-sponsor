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
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

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

_UNWANTED_CAREERS_RE = re.compile(
    r"savedvacancies|saved-jobs|saved jobs|favourites|favorites|wishlist|bookmark|"
    r"my-account|account|login|register",
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
        self._last_action_log: list[dict] = []

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

        # If the provided URL already looks like a listing page, keep it unless
        # it is a personalised/saved page variant.
        current_url = await self._browser.get_current_url()
        if _CAREERS_KEYWORDS.search(current_url) and not _UNWANTED_CAREERS_RE.search(current_url):
            cleaned = self._clean_careers_url(current_url)
            logger.info("Using current careers URL directly: {}", cleaned)
            if cleaned != current_url:
                await self._browser.navigate(cleaned)
            return cleaned

        # ── Step 2: quick heuristic check before calling the LLM ─────────
        careers_url = await self._heuristic_find()
        if careers_url:
            cleaned = self._clean_careers_url(careers_url)
            logger.info("Heuristic found careers page: {}", cleaned)
            await self._browser.navigate(cleaned)
            return cleaned

        # ── Step 3: delegate to BrowserAgent ─────────────────────────────
        task = (
            f"Navigate to the Careers or Jobs page of the company at {start_url}. "
            "The page may be labelled: Careers, Jobs, Join Us, Work With Us, "
            "Opportunities, Hiring, Vacancies, Open Positions, We're Hiring. "
            "Find the public live vacancies listing page, not personalised pages such as "
            "Saved Vacancies, Saved Jobs, Favourites, account, login, or register pages. "
            "Avoid URLs with query parameters like SavedVacancies=true. "
            "Once you are on the careers listing page, call done(result=<current_url>)."
        )
        result = await self._browser_agent.run(task)
        self._last_action_log = self._browser_agent.action_log

        if result:
            final_url = self._clean_careers_url(str(result))
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
        final_url = self._clean_careers_url(final_url)
        if _CAREERS_KEYWORDS.search(final_url) and not _UNWANTED_CAREERS_RE.search(final_url):
            logger.info("Browser is on a careers URL: {}", final_url)
            return final_url

        logger.error("Could not locate careers page for: {}", start_url)
        return None

    @property
    def last_action_log(self) -> list[dict]:
        return list(self._last_action_log)

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
            if not href or _UNWANTED_CAREERS_RE.search(href) or _UNWANTED_CAREERS_RE.search(text):
                continue
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
        return self._clean_careers_url(scored[0][1])

    @staticmethod
    def _clean_careers_url(url: str) -> str:
        """
        Remove personalised/saved query params from otherwise valid listing URLs.
        """
        parsed = urlparse(url)
        if not parsed.query:
            return url

        blocked = {
            "savedvacancies",
            "savedjobs",
            "saved_jobs",
            "favourites",
            "favorites",
            "wishlist",
        }
        cleaned_q = [
            (k, v)
            for k, v in parse_qsl(parsed.query, keep_blank_values=True)
            if k.lower() not in blocked
        ]
        return urlunparse(parsed._replace(query=urlencode(cleaned_q)))
