from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any
from urllib.parse import urlparse

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from agent import AIAgent
from browser import BrowserManager, browser_session
from career_finder import CareerFinder
from job_scraper import JobScraper
from platform_backend.models import ActionEvent, Company, CrawlRun, Job
from platform_backend.services.ats_detector import detect_ats
from platform_backend.services.cache_service import CacheService
from platform_backend.services.event_hub import EventHub
from platform_backend.services.workflow_service import WorkflowService
from tools import Tool, ToolExecutor


class CrawlOrchestrator:
    def __init__(
        self,
        *,
        session_factory: async_sessionmaker,
        event_hub: EventHub,
        max_jobs_per_company: int,
    ) -> None:
        self._session_factory = session_factory
        self._event_hub = event_hub
        self._max_jobs_per_company = max_jobs_per_company
        self._cache = CacheService()
        self._workflow = WorkflowService()

    async def process_company(self, company_name: str, homepage_url: str) -> None:
        domain = self._extract_domain(homepage_url)
        company_id = await self._upsert_company(company_name, domain, homepage_url)
        run_id = await self._create_run(company_id)

        await self._emit(company_id, run_id, "queue.started", f"Started crawl for {company_name}")

        try:
            careers_url, ats_from_cache = await self._resolve_careers_url(
                company_id=company_id,
                run_id=run_id,
                domain=domain,
                company_name=company_name,
                homepage_url=homepage_url,
            )

            if not careers_url:
                raise RuntimeError("Could not find careers page")

            jobs, ats_detected = await self._scrape_jobs(
                company_id=company_id,
                run_id=run_id,
                company_name=company_name,
                careers_url=careers_url,
            )
            ats_provider = ats_detected or ats_from_cache

            await self._save_jobs(company_id, jobs, ats_provider)
            await self._save_company_outcome(company_id, careers_url, ats_provider)
            async with self._session_factory() as session:
                await self._cache.upsert(
                    session,
                    domain=domain,
                    careers_url=careers_url,
                    ats_provider=ats_provider,
                )

            await self._finish_run(run_id, "completed", f"Saved {len(jobs)} jobs")
            await self._emit(company_id, run_id, "queue.completed", f"Completed crawl, saved {len(jobs)} jobs")
        except Exception as exc:
            logger.exception("Crawl failed for {}", homepage_url)
            await self._finish_run(run_id, "failed", str(exc))
            await self._emit(company_id, run_id, "queue.failed", str(exc))

    async def _resolve_careers_url(
        self,
        *,
        company_id: int,
        run_id: int,
        domain: str,
        company_name: str,
        homepage_url: str,
    ) -> tuple[str | None, str | None]:
        async with self._session_factory() as session:
            cache_item = await self._cache.get(session, domain)
        if cache_item and cache_item.careers_url:
            await self._emit(company_id, run_id, "cache.hit", f"Using cached careers URL: {cache_item.careers_url}")
            return cache_item.careers_url, cache_item.ats_provider

        async with browser_session() as browser:
            action_listener = self._build_action_listener(company_id, run_id)
            browser.set_action_listener(action_listener)
            agent = AIAgent()

            replay_url = await self._try_replay_workflow(browser, domain, company_id, run_id)
            if replay_url:
                return replay_url, None

            await self._emit(company_id, run_id, "crawl.homepage", "Opening homepage")
            finder = CareerFinder(browser=browser, agent=agent)
            careers_url = await finder.find(homepage_url)
            if careers_url:
                replay_actions = self._workflow_actions_from_log(finder.last_action_log)
                if replay_actions:
                    async with self._session_factory() as session:
                        await self._workflow.save_success_workflow(
                            session,
                            domain=domain,
                            careers_url=careers_url,
                            actions=replay_actions,
                        )
                await self._emit(company_id, run_id, "crawl.careers", f"Found careers page: {careers_url}")
            return careers_url, None

    async def _try_replay_workflow(
        self,
        browser: BrowserManager,
        domain: str,
        company_id: int,
        run_id: int,
    ) -> str | None:
        async with self._session_factory() as session:
            workflow = await self._workflow.get_for_domain(session, domain)
        if not workflow:
            return None

        executor = ToolExecutor(browser)
        actions = self._workflow.parse_actions(workflow)[:12]
        if not actions:
            return workflow.careers_url

        await self._emit(company_id, run_id, "workflow.replay", f"Replaying {len(actions)} actions")
        for action in actions:
            tool = str(action.get("tool", ""))
            args = action.get("args", {})
            if tool not in {Tool.GOTO, Tool.CLICK, Tool.SCROLL, Tool.WAIT, Tool.DISMISS_POPUP}:
                continue
            result = await executor.execute(tool, args if isinstance(args, dict) else {})
            if not result.success:
                return None

        current_url = await browser.get_current_url()
        if current_url:
            return current_url
        return workflow.careers_url

    async def _scrape_jobs(
        self,
        *,
        company_id: int,
        run_id: int,
        company_name: str,
        careers_url: str,
    ) -> tuple[list[dict[str, Any]], str | None]:
        async with browser_session() as browser:
            action_listener = self._build_action_listener(company_id, run_id)
            browser.set_action_listener(action_listener)
            agent = AIAgent()
            scraper = JobScraper(
                browser=browser,
                agent=agent,
                company=company_name,
                max_jobs=self._max_jobs_per_company,
            )
            await self._emit(company_id, run_id, "crawl.jobs", "Scraping jobs")
            jobs = await scraper.scrape(careers_url)
            page_html = await browser.get_page_html()
            ats_provider = detect_ats(url=careers_url, html=page_html)
            return jobs, ats_provider

    async def _save_jobs(self, company_id: int, jobs: list[dict[str, Any]], ats_provider: str | None) -> None:
        async with self._session_factory() as session:
            for row in jobs:
                dedupe_hash = self._job_hash(company_id, row)
                exists = await session.execute(select(Job.id).where(Job.dedupe_hash == dedupe_hash))
                if exists.scalar_one_or_none() is not None:
                    continue
                session.add(
                    Job(
                        company_id=company_id,
                        source_url=row.get("apply_url") or row.get("job_url") or "",
                        apply_url=row.get("apply_url") or None,
                        title=row.get("job_title") or "Untitled role",
                        location=row.get("location") or None,
                        department=row.get("department") or None,
                        employment_type=row.get("employment_type") or None,
                        salary=row.get("salary") or None,
                        description=row.get("job_description") or None,
                        required_skills=row.get("required_skills") or None,
                        preferred_skills=row.get("preferred_skills") or None,
                        visa_sponsorship=row.get("visa_sponsorship") or None,
                        ats_provider=ats_provider,
                        dedupe_hash=dedupe_hash,
                    )
                )
            await session.commit()

    async def _save_company_outcome(self, company_id: int, careers_url: str, ats_provider: str | None) -> None:
        async with self._session_factory() as session:
            company = await session.get(Company, company_id)
            if company is None:
                return
            company.careers_url = careers_url
            company.ats_provider = ats_provider
            await session.commit()

    async def _upsert_company(self, name: str, domain: str, homepage_url: str) -> int:
        async with self._session_factory() as session:
            result = await session.execute(select(Company).where(Company.domain == domain))
            company = result.scalar_one_or_none()
            if company:
                company.name = name
                company.homepage_url = homepage_url
                await session.commit()
                return company.id

            company = Company(name=name, domain=domain, homepage_url=homepage_url)
            session.add(company)
            await session.commit()
            await session.refresh(company)
            return company.id

    async def _create_run(self, company_id: int) -> int:
        async with self._session_factory() as session:
            run = CrawlRun(company_id=company_id, status="running")
            session.add(run)
            await session.commit()
            await session.refresh(run)
            return run.id

    async def _finish_run(self, run_id: int, status: str, message: str) -> None:
        async with self._session_factory() as session:
            run = await session.get(CrawlRun, run_id)
            if run is None:
                return
            run.status = status
            run.message = message
            run.finished_at = datetime.utcnow()
            await session.commit()

    async def _emit(self, company_id: int | None, run_id: int | None, action_type: str, details: str) -> None:
        async with self._session_factory() as session:
            session.add(
                ActionEvent(
                    company_id=company_id,
                    run_id=run_id,
                    action_type=action_type,
                    details=details,
                )
            )
            await session.commit()

        await self._event_hub.publish(
            {
                "company_id": company_id,
                "run_id": run_id,
                "action_type": action_type,
                "details": details,
                "timestamp": datetime.utcnow().isoformat(),
            }
        )

    def _build_action_listener(self, company_id: int, run_id: int):
        async def _listener(payload: dict[str, Any]) -> None:
            action = payload.get("action", "browser.action")
            details = str(payload.get("details", ""))[:1000]
            await self._emit(company_id, run_id, action, details)

        return _listener

    @staticmethod
    def _workflow_actions_from_log(action_log: list[dict[str, Any]]) -> list[dict[str, Any]]:
        actions: list[dict[str, Any]] = []
        for entry in action_log:
            decision = entry.get("decision") or {}
            tool = decision.get("tool")
            args = decision.get("args", {})
            if not tool or not isinstance(args, dict):
                continue
            actions.append({"tool": str(tool), "args": args})
        return actions

    @staticmethod
    def _extract_domain(url: str) -> str:
        host = urlparse(url).netloc.lower()
        if host.startswith("www."):
            host = host[4:]
        return host

    @staticmethod
    def _job_hash(company_id: int, job: dict[str, Any]) -> str:
        base = "|".join(
            [
                str(company_id),
                (job.get("job_title") or "").strip().lower(),
                (job.get("location") or "").strip().lower(),
                (job.get("apply_url") or "").strip().lower(),
            ]
        )
        return hashlib.sha256(base.encode("utf-8")).hexdigest()
