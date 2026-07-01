"""
job_scraper.py — Discovers and extracts individual job postings.

Phase 2: domain-specific LLM prompts are kept here; the agent's generic
decide_action() is used for browser navigation, and call_with_prompt() is
used for structured extraction tasks (link discovery, detail extraction).

Workflow:
  1. Start from the careers listing page.
  2. Ask the AI to identify all individual job URLs on the page.
  3. For each URL, navigate to it, ask the AI to extract structured data.
  4. Handle pagination if more pages exist.
  5. Return a list of job dicts ready for CSV export.
"""

from __future__ import annotations

import asyncio
import re
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
from loguru import logger

from agent import AIAgent
from browser import BrowserManager

# How long to wait between job-page requests (seconds) — be polite to servers
_REQUEST_DELAY: float = 1.5

# Maximum number of jobs to scrape in a single run (safety cap)
_MAX_JOBS: int = 200

# Regex patterns that usually indicate a "next page" / pagination link
_NEXT_PAGE_RE = re.compile(r"\bnext\b|\bnext page\b|›|»|>", re.IGNORECASE)

# ── Domain-specific prompts ───────────────────────────────────────────────────

_JOB_LIST_SYSTEM = """
You are an expert web-analysis AI. Given the HTML / text of a careers listing
page, identify all job postings and return ONLY valid JSON (no markdown):

{
  "job_links": [
    {"title": "...", "url": "..."},
    ...
  ]
}

Include every individual job posting URL you find. Do not include category pages,
pagination links, or filter controls — only actual job listings.
If no individual jobs are found (e.g. it's still a category landing page), return
{"job_links": []}.
"""

_EXTRACTION_SYSTEM = """
You are an expert job-data extraction AI. Given the HTML / text of a job posting
page, extract structured information and return ONLY valid JSON (no markdown).

Return exactly this structure (use null for missing fields):
{
  "job_title": "...",
  "location": "...",
  "department": "...",
  "employment_type": "...",
  "salary": "...",
  "job_description": "...",
  "required_skills": ["..."],
  "preferred_skills": ["..."],
  "visa_sponsorship": "...",
  "apply_url": "..."
}

For visa_sponsorship, look for:
- Explicit mention of visa sponsorship, right-to-work requirements, or work
  authorisation statements.
- If nothing is mentioned, return null.
- Summarise concisely (e.g. "Visa sponsorship available", "No sponsorship offered",
  "Applicants must have the right to work in the UK").
"""


class JobScraper:
    """
    Extracts structured job data from a careers listing page.

    Usage::

        scraper = JobScraper(browser_manager, ai_agent, company_name="Acme")
        jobs = await scraper.scrape(careers_url)
    """

    def __init__(self, browser: BrowserManager, agent: AIAgent, company: str) -> None:
        self._browser = browser
        self._agent = agent
        self._company = company

    # ── Public API ────────────────────────────────────────────────────────────

    async def scrape(self, careers_url: str) -> list[dict]:
        """
        Discover and extract all jobs starting from *careers_url*.
        Returns a list of job dicts.
        """
        logger.info("Starting job scrape from: {}", careers_url)
        all_jobs: list[dict] = []
        visited_listing_urls: set[str] = set()
        current_listing_url: str | None = careers_url

        while current_listing_url and len(all_jobs) < _MAX_JOBS:
            if current_listing_url in visited_listing_urls:
                logger.debug("Already visited listing: {}", current_listing_url)
                break
            visited_listing_urls.add(current_listing_url)

            # Navigate to the listing page
            await self._browser.navigate(current_listing_url)
            logger.info("Scraping listing page: {}", current_listing_url)

            page_text = await self._browser.get_page_text()
            page_html = await self._browser.get_page_html()

            # Ask AI to extract job links
            job_links = await self._extract_job_links(page_text, page_html, current_listing_url)

            # Fallback: try BeautifulSoup heuristic extraction
            if not job_links:
                logger.info("AI found no job links; trying heuristic extraction.")
                job_links = self._heuristic_job_links(page_html, current_listing_url)

            logger.info("Found {} job link(s) on this page.", len(job_links))

            # Scrape each individual job
            for job_link in job_links:
                if len(all_jobs) >= _MAX_JOBS:
                    break

                job_url = job_link.get("url", "")
                job_title_hint = job_link.get("title", "")

                if not job_url:
                    continue
                job_url = self._ensure_absolute(job_url, current_listing_url)

                logger.info("Opening job: {} — {}", job_title_hint or "(untitled)", job_url)
                job_data = await self._extract_single_job(job_url)
                if job_data:
                    all_jobs.append(job_data)
                    logger.success(
                        "Extracted job {}/{}: '{}'",
                        len(all_jobs),
                        _MAX_JOBS,
                        job_data.get("job_title", "?"),
                    )

                await asyncio.sleep(_REQUEST_DELAY)

                # Return to listings
                logger.debug("Returning to listings page.")
                await self._browser.navigate(current_listing_url)

            # Check for a "Next page" link
            current_listing_url = await self._find_next_page(
                current_listing_url, visited_listing_urls
            )

        logger.info("Scraping complete. Total jobs extracted: {}", len(all_jobs))
        return all_jobs

    # ── Private helpers ───────────────────────────────────────────────────────

    async def _extract_job_links(
        self, page_text: str, page_html: str, current_url: str
    ) -> list[dict]:
        """Ask the LLM to identify individual job URLs on the listing page."""
        user_prompt = (
            f"Current URL: {current_url}\n\n"
            f"=== PAGE TEXT (first 4000 chars) ===\n{page_text[:4000]}\n\n"
            f"=== PAGE HTML SNIPPET (first 6000 chars) ===\n{page_html[:6000]}\n\n"
            "Return all individual job listing URLs you can find."
        )
        data = await self._agent.call_with_prompt(_JOB_LIST_SYSTEM, user_prompt)
        return data.get("job_links", [])

    async def _extract_single_job(self, url: str) -> dict | None:
        """Navigate to a job page and extract structured data via the AI."""
        try:
            await self._browser.navigate(url)
            await self._browser.scroll_to_bottom()

            page_text = await self._browser.get_page_text()
            page_html = await self._browser.get_page_html()

            user_prompt = (
                f"Company: {self._company}\n"
                f"Job URL: {url}\n\n"
                f"=== PAGE TEXT (first 5000 chars) ===\n{page_text[:5000]}\n\n"
                f"=== PAGE HTML SNIPPET (first 8000 chars) ===\n{page_html[:8000]}\n\n"
                "Extract all job details."
            )
            raw = await self._agent.call_with_prompt(_EXTRACTION_SYSTEM, user_prompt)

            if not raw:
                logger.warning("Empty extraction for: {}", url)
                return None

            job = {
                "company": self._company,
                "job_title": raw.get("job_title") or "",
                "location": raw.get("location") or "",
                "department": raw.get("department") or "",
                "employment_type": raw.get("employment_type") or "",
                "salary": raw.get("salary") or "",
                "job_description": self._clean_text(raw.get("job_description") or ""),
                "required_skills": self._join_list(raw.get("required_skills")),
                "preferred_skills": self._join_list(raw.get("preferred_skills")),
                "visa_sponsorship": raw.get("visa_sponsorship") or "",
                "apply_url": raw.get("apply_url") or url,
            }
            return job

        except Exception as exc:
            logger.error("Error extracting job at {}: {}", url, exc)
            return None

    async def _find_next_page(
        self, current_url: str, visited: set[str]
    ) -> str | None:
        """
        Look for a 'Next page' link on the current listing page.
        Returns the next listing URL, or None.
        """
        try:
            all_links = await self._browser.get_all_links()
            for link in all_links:
                text = link.get("text", "")
                href = link.get("href", "")
                if _NEXT_PAGE_RE.search(text) and href:
                    next_url = self._ensure_absolute(href, current_url)
                    if next_url not in visited:
                        logger.info("Found next page: {}", next_url)
                        return next_url
        except Exception as exc:
            logger.warning("Error looking for next page: {}", exc)
        return None

    @staticmethod
    def _heuristic_job_links(html: str, base_url: str) -> list[dict]:
        """
        BeautifulSoup fallback: find <a> tags that look like job postings.
        """
        soup = BeautifulSoup(html, "lxml")
        base_path = urlparse(base_url).path.rstrip("/")
        results: list[dict] = []
        seen: set[str] = set()

        containers = soup.find_all(
            lambda tag: tag.name in {"li", "article", "div"}
            and any(
                kw in " ".join(tag.get("class", [])).lower()
                for kw in ("job", "position", "opening", "role", "vacancy", "listing", "card")
            )
        )

        if not containers:
            containers = [soup]

        for container in containers:
            for a in container.find_all("a", href=True):
                href = a["href"]
                if href.startswith("#") or href.startswith("javascript:"):
                    continue
                abs_href = urljoin(base_url, href)
                link_path = urlparse(abs_href).path.rstrip("/")

                if link_path == base_path:
                    continue
                if abs_href in seen:
                    continue
                seen.add(abs_href)

                text = (a.get_text(separator=" ") or "").strip()
                if len(text.split()) >= 2:
                    results.append({"title": text[:120], "url": abs_href})

        return results

    @staticmethod
    def _ensure_absolute(url: str, base: str) -> str:
        if url.startswith(("http://", "https://")):
            return url
        return urljoin(base, url)

    @staticmethod
    def _clean_text(text: str) -> str:
        return re.sub(r"\s+", " ", text).strip()

    @staticmethod
    def _join_list(value: object) -> str:
        if isinstance(value, list):
            return " | ".join(str(v) for v in value if v)
        if isinstance(value, str):
            return value
        return ""
