"""
main.py — Entry point for the AI Career Discovery & Job Scraper.

Phase 2: the pipeline now goes through the generic BrowserAgent for all
browser-driving decisions.  Career-specific logic stays in career_finder.py
and job_scraper.py; the AI layer in agent.py is fully domain-agnostic.

Usage:
    python main.py <company_url> [--company "Company Name"]

Example:
    python main.py https://www.bbc.co.uk --company "BBC"
    python main.py https://careers.google.com

The script will:
  1. Launch a visible Chromium browser.
  2. Use BrowserAgent (observe→reason→act loop) to find the Careers page.
  3. Extract all job postings from that page.
  4. Export the results to output/jobs.csv.
  5. Save a JSON action log to output/action_log_<timestamp>.json.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from urllib.parse import urlparse

from dotenv import load_dotenv
from loguru import logger

load_dotenv()

# ── Logging configuration ─────────────────────────────────────────────────────
logger.remove()
logger.add(
    sys.stderr,
    format=(
        "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{line}</cyan> — <level>{message}</level>"
    ),
    level="INFO",
    colorize=True,
)
logger.add(
    "output/scraper_{time:YYYYMMDD_HHmmss}.log",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{line} — {message}",
    level="DEBUG",
    rotation="10 MB",
    retention="7 days",
)


# ── Main coroutine ────────────────────────────────────────────────────────────


async def run(company_url: str, company_name: str) -> None:
    """
    Full pipeline:
      open browser → BrowserAgent finds careers page → scrape jobs → export CSV.
    """
    from agent import AIAgent
    from browser import browser_session
    from career_finder import CareerFinder
    from csv_exporter import CSVExporter
    from job_scraper import JobScraper

    logger.info("=" * 60)
    logger.info("AI Career Discovery & Job Scraper  [Phase 2 — BrowserAgent]")
    logger.info("Company URL : {}", company_url)
    logger.info("Company Name: {}", company_name)
    logger.info("=" * 60)

    agent = AIAgent()
    exporter = CSVExporter()

    async with browser_session() as browser:
        # ── Phase 1: BrowserAgent navigates to the careers page ──────────
        finder = CareerFinder(browser=browser, agent=agent)
        careers_url = await finder.find(company_url)

        if not careers_url:
            logger.error(
                "Could not locate a careers page for {}. Aborting.", company_url
            )
            sys.exit(1)

        logger.success("Careers page located: {}", careers_url)

        # ── Phase 2: scrape all jobs ─────────────────────────────────────
        scraper = JobScraper(browser=browser, agent=agent, company=company_name)
        jobs = await scraper.scrape(careers_url)

        if not jobs:
            logger.warning(
                "No jobs were extracted from {}. The page may use a JS framework "
                "that renders asynchronously, or there are no open positions.",
                careers_url,
            )

        # ── Phase 3: export to CSV ───────────────────────────────────────
        output_path = exporter.export(jobs, company=company_name)

        logger.info("=" * 60)
        logger.success("Done! {} job(s) saved to: {}", len(jobs), output_path)
        logger.info("Action logs and screenshots saved to: output/")
        logger.info("=" * 60)


# ── CLI argument parsing ──────────────────────────────────────────────────────


def _infer_company_name(url: str) -> str:
    """Derive a human-readable company name from the URL if none is given."""
    host = urlparse(url).netloc
    for prefix in ("www.", "careers.", "jobs.", "en."):
        if host.startswith(prefix):
            host = host[len(prefix):]
    name = host.split(".")[0]
    return name.replace("-", " ").replace("_", " ").title()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="AI-powered career page discovery and job scraper (Phase 2).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python main.py https://www.bbc.co.uk\n"
            "  python main.py https://careers.google.com --company Google\n"
        ),
    )
    parser.add_argument(
        "url",
        help="Company homepage or careers URL to start from.",
    )
    parser.add_argument(
        "--company",
        default=None,
        help=(
            "Human-readable company name for the CSV output. "
            "Inferred from the URL if not provided."
        ),
    )
    return parser.parse_args(argv)


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    args = parse_args()
    company = args.company or _infer_company_name(args.url)
    try:
        asyncio.run(run(company_url=args.url, company_name=company))
    except KeyboardInterrupt:
        logger.warning("Interrupted by user.")
        sys.exit(0)
