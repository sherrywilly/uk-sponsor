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
_MAX_JOBS: int = 5

# Regex patterns that usually indicate a "next page" / pagination link
_NEXT_PAGE_RE = re.compile(r"\bnext\b|\bnext page\b|›|»|>", re.IGNORECASE)
_JOB_URL_HINT_RE = re.compile(
    r"job|jobs|vacanc|career|role|position|opening|requisition|req|apply",
    re.IGNORECASE,
)
_NON_JOB_URL_RE = re.compile(
    r"about|contact|privacy|cookie|terms|sitemap|benefit|reward|why-join|care-home|locations?",
    re.IGNORECASE,
)

# ── Domain-specific prompts ───────────────────────────────────────────────────

_JOB_LIST_SYSTEM = r"""
You are a job-link classifier. I will give you a numbered list of page links
extracted from a careers/vacancies listing page.

Your task: return ONLY those links that are individual job postings.

Return ONLY valid JSON (no markdown, no explanation):
{
  "job_links": [
    {"title": "<job title>", "url": "<full url>"},
    ...
  ]
}

Classification rules:
- INCLUDE: links whose URL or title contains a specific job title, role name,
  job ID, vacancy ID, or requisition number.
- INCLUDE: URLs matching patterns like /job/123, /vacancy/456, /apply/789,
  /sys-\d+-role-name, ?jobid=, ?vacancyid=, /req/.
- EXCLUDE: navigation links, category pages, filter links, pagination,
  home/about/contact/benefits/why-join/care-homes/locations pages.
- EXCLUDE: URLs that are identical to the current listing page URL.

Example — INCLUDE:
  {"title": "Registered Nurse - London", "url": "https://example.com/jobs/12345"}

Example — EXCLUDE:
  {"title": "Why Join Us", "url": "https://example.com/careers/why-join"}

If no individual jobs exist in the list, return {"job_links": []}.
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

_NEXT_PAGE_SYSTEM = """
You are an expert web-navigation AI. Given a job-listing page HTML/text, find the
URL of the next listings page (pagination).

Return ONLY valid JSON (no markdown):
{
    "next_page_url": "..."  // absolute or relative URL, or null if none
}

Rules:
- Return null if there is no next page.
- Do not return the current page URL.
- Do not return job-detail URLs; only listing pagination URL.
"""


class JobScraper:
    """
    Extracts structured job data from a careers listing page.

    Usage::

        scraper = JobScraper(browser_manager, ai_agent, company_name="Acme")
        jobs = await scraper.scrape(careers_url)
    """

    def __init__(
        self,
        browser: BrowserManager,
        agent: AIAgent,
        company: str,
        max_jobs: int = _MAX_JOBS,
    ) -> None:
        self._browser = browser
        self._agent = agent
        self._company = company
        self._max_jobs = max(1, max_jobs)

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

        while current_listing_url and len(all_jobs) < self._max_jobs:
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
                if len(all_jobs) >= self._max_jobs:
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
                        self._max_jobs,
                        job_data.get("job_title", "?"),
                    )

                await asyncio.sleep(_REQUEST_DELAY)

                # Return to listings
                logger.debug("Returning to listings page.")
                await self._browser.navigate(current_listing_url)

            # Check for a "Next page" link
            next_listing_url = await self._find_next_page(
                current_listing_url, visited_listing_urls
            )
            if not next_listing_url:
                next_listing_url = await self._find_next_page_with_ai(
                    page_text=page_text,
                    page_html=page_html,
                    current_url=current_listing_url,
                    visited=visited_listing_urls,
                )

            current_listing_url = next_listing_url

        logger.info("Scraping complete. Total jobs extracted: {}", len(all_jobs))
        return all_jobs

    # ── Private helpers ───────────────────────────────────────────────────────

    async def _extract_job_links(
        self, page_text: str, page_html: str, current_url: str
    ) -> list[dict]:
        """Ask the LLM to identify individual job URLs on the listing page."""
        # Pre-extract all links with BeautifulSoup so the model gets a
        # clean numbered list instead of raw HTML — much easier to classify.
        soup = BeautifulSoup(page_html, "lxml")
        raw_links: list[dict] = []
        seen: set[str] = set()
        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            if href.startswith(("#", "javascript:", "mailto:", "tel:")):
                continue
            abs_href = self._ensure_absolute(href, current_url)
            if abs_href in seen:
                continue
            seen.add(abs_href)
            title = (a.get_text(separator=" ") or "").strip()[:120]
            raw_links.append({"title": title, "url": abs_href})

        if not raw_links:
            return []

        # Format as a numbered list for the LLM
        numbered = "\n".join(
            f"{i+1}. [{item['title'] or '(no text)'}] {item['url']}"
            for i, item in enumerate(raw_links[:200])
        )
        user_prompt = (
            f"Current listing page URL: {current_url}\n\n"
            f"Links found on page ({len(raw_links)} total, showing first 200):\n"
            f"{numbered}\n\n"
            "Classify which of these are individual job postings."
        )
        data = await self._agent.call_with_prompt(_JOB_LIST_SYSTEM, user_prompt)
        links = data.get("job_links", [])
        return self._filter_probable_job_links(links, current_url)

    # Known content-ready selectors for common JS-heavy job portals
    _JS_FRAMEWORK_SELECTORS: list[str] = [
        # Workday
        "[data-automation-id='jobPostingHeader']",
        "[data-automation-id='job-posting-details']",
        "[data-automation-id='richTextContent']",
        # Greenhouse
        "#app_body", "#main",
        # Lever
        ".content-wrapper",
        # SmartRecruiters
        ".job-details",
        # Generic fallback
        "article", "main",
    ]

    async def _extract_single_job(self, url: str) -> dict | None:
        """Navigate to a job page and extract structured data via the AI."""
        try:
            await self._browser.navigate(url)

            # Extra wait for JS-rendered portals (Workday, Greenhouse, etc.)
            await self._browser.wait_for_selector_any(self._JS_FRAMEWORK_SELECTORS)
            await self._browser.scroll_to_bottom()

            page_text = await self._browser.get_page_text()
            page_html = await self._browser.get_page_html()

            # If page text is still empty, wait a bit more and retry once
            if not page_text.strip():
                logger.warning("Page text empty after JS wait; retrying in 3s: {}", url)
                await self._browser.page.wait_for_timeout(3_000)
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

            if not self._is_meaningful_job(job):
                logger.warning("Skipping non-job/empty extraction for: {}", url)
                return None

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

    async def _find_next_page_with_ai(
        self,
        page_text: str,
        page_html: str,
        current_url: str,
        visited: set[str],
    ) -> str | None:
        """
        LLM fallback for pagination detection when regex/link heuristics fail.
        """
        try:
            visited_list = sorted(list(visited))[-30:]
            user_prompt = (
                f"Current URL: {current_url}\n"
                f"Visited listing URLs: {visited_list}\n\n"
                f"=== PAGE TEXT (first 4000 chars) ===\n{page_text[:4000]}\n\n"
                f"=== PAGE HTML SNIPPET (first 8000 chars) ===\n{page_html[:8000]}\n\n"
                "Find the next listing page URL, if one exists."
            )
            data = await self._agent.call_with_prompt(_NEXT_PAGE_SYSTEM, user_prompt)
            raw_url = data.get("next_page_url")
            if not raw_url:
                return None

            next_url = self._ensure_absolute(str(raw_url), current_url)
            if next_url == current_url or next_url in visited:
                return None

            logger.info("AI found next page: {}", next_url)
            return next_url
        except Exception as exc:
            logger.warning("AI next-page detection failed: {}", exc)
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

    def _filter_probable_job_links(self, links: list[dict], current_url: str) -> list[dict]:
        """Remove obvious non-job links from LLM/heuristic candidates."""
        cleaned: list[dict] = []
        seen: set[str] = set()

        for link in links:
            raw_url = str(link.get("url", "")).strip()
            title = str(link.get("title", "")).strip()
            if not raw_url:
                continue

            abs_url = self._ensure_absolute(raw_url, current_url)
            if abs_url in seen:
                continue

            if self._is_probable_job_link(abs_url, title, current_url):
                cleaned.append({"title": title, "url": abs_url})
                seen.add(abs_url)

        return cleaned

    def _is_probable_job_link(self, url: str, title: str, current_url: str) -> bool:
        """Conservative check to reduce navigation/footer links misclassified as jobs."""
        url_l = url.lower()
        title_l = title.lower()
        current_l = current_url.lower().rstrip("/")

        if url_l.rstrip("/") == current_l:
            return False
        if _NON_JOB_URL_RE.search(url_l) or _NON_JOB_URL_RE.search(title_l):
            return False

        # Strong positive signals in URL/title.
        if _JOB_URL_HINT_RE.search(url_l) or _JOB_URL_HINT_RE.search(title_l):
            return True

        # IDs in query/path often indicate a specific posting.
        if re.search(r"jobid=|vacancyid=|id=\d+|/\d{4,}", url_l):
            return True

        return False

    @staticmethod
    def _is_meaningful_job(job: dict) -> bool:
        """Reject empty records so non-job pages cannot be exported as jobs."""
        non_url_values = [
            str(job.get("job_title", "")).strip(),
            str(job.get("location", "")).strip(),
            str(job.get("department", "")).strip(),
            str(job.get("employment_type", "")).strip(),
            str(job.get("salary", "")).strip(),
            str(job.get("visa_sponsorship", "")).strip(),
            str(job.get("required_skills", "")).strip(),
            str(job.get("preferred_skills", "")).strip(),
            str(job.get("job_description", "")).strip(),
        ]
        return any(non_url_values)

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
