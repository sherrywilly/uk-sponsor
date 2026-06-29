from __future__ import annotations

import asyncio
import base64
import json
import time
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any

from loguru import logger
from playwright.async_api import Browser, BrowserContext, Page, async_playwright

from .ats import detect_ats_type, domain_from_url
from .claude_client import ClaudeClient
from .cv_tailor import CVTailor
from .database import Database
from .executor import FormExecutor
from .html_extractor import extract_form_fields
from .jd_extractor import extract_jd
from .recorder import ActionRecorder, ActionReplayer


class JobAgent:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.claude = ClaudeClient(db)
        self.cv_tailor = CVTailor(self.claude)
        self.executor = FormExecutor()

    @asynccontextmanager
    async def _browser_page(self):
        async with async_playwright() as p:
            browser: Browser = await p.chromium.launch(headless=True)
            context: BrowserContext = await browser.new_context()
            page: Page = await context.new_page()
            try:
                yield page
            finally:
                await context.close()
                await browser.close()

    async def process_job(self, url: str, profile: dict[str, Any]) -> dict[str, Any]:
        started = time.monotonic()
        domain = domain_from_url(url)
        ats_type = detect_ats_type(url)

        await self.db.insert_job(
            {
                "url": url,
                "domain": domain,
                "company": domain,
                "job_title": "Unknown",
                "ats_type": ats_type,
                "status": "started",
                "applied_at": None,
            }
        )

        async with self._browser_page() as page:
            await page.goto(url, wait_until="domcontentloaded", timeout=60_000)

            jd = extract_jd(await page.content())
            if jd.sponsorship_flag == "blocked":
                await self.db.update_job(url, {"status": "skipped", "notes": "no sponsorship"})
                return {"status": "skipped", "reason": "no_sponsorship"}

            replayer = ActionReplayer(self.db)
            if await replayer.can_replay(url):
                replay_result = await replayer.replay(page, url, profile, cv_path="")
                if replay_result.status == "submitted":
                    await self.db.update_job(
                        url,
                        {
                            "status": "submitted",
                            "replay_used": 1,
                            "recording_id": replay_result.recording_id,
                            "applied_at": datetime.utcnow().isoformat(),
                            "duration_seconds": time.monotonic() - started,
                        },
                    )
                    return replay_result.model_dump()

            tailor_result = await self.cv_tailor.tailor(company=domain, jd=jd)
            cover_letter = await self.claude.generate_cover_letter(
                company=domain,
                role="Software Engineer",
                jd_keywords=jd.compressed.tech_stack,
                profile_summary=json.dumps(profile)[:400],
            )

            html = await page.inner_html("body")
            fields = extract_form_fields(html)

            recorder = ActionRecorder(self.db)
            recorder.start(domain, ats_type)

            if fields:
                actions = await self.claude.extract_form_actions(fields, profile)
            else:
                screenshot = await page.screenshot(type="jpeg", quality=70)
                screenshot_b64 = base64.b64encode(screenshot).decode("utf-8")
                actions = await self.claude.extract_form_actions_vision(screenshot_b64, profile)

            page_num = 0
            result = None
            while page_num < 10:
                result = await self.executor.execute(
                    page=page,
                    actions=actions,
                    profile=profile,
                    cv_path=tailor_result.pdf_path or tailor_result.cv_path,
                    recorder=recorder,
                )
                if result.status in {"submitted", "failed", "captcha", "manual_review"}:
                    break
                if result.status == "next_page":
                    old = page.url
                    html = await page.inner_html("body")
                    fields = extract_form_fields(html)
                    actions = await self.claude.extract_form_actions(fields or {"f": []}, profile)
                    recorder.record_page_transition(old, page.url)
                    page_num += 1

            recording_id = None
            if result and result.status == "submitted":
                recording_id = await recorder.save(success=True, success_signal=result.success_signal)

            duration = time.monotonic() - started
            costs = await self.db.get_cost_breakdown()
            total_tokens_input = sum(int(row.get("input_tokens", 0)) for row in costs)
            total_tokens_output = sum(int(row.get("output_tokens", 0)) for row in costs)
            total_tokens_cached = sum(int(row.get("cached_tokens", 0)) for row in costs)
            total_cost = sum(float(row.get("cost", 0)) for row in costs)

            await self.db.update_job(
                url,
                {
                    "status": result.status if result else "failed",
                    "jd_summary": jd.compressed.model_dump_json(),
                    "jd_keywords": json.dumps(jd.compressed.tech_stack),
                    "match_score": tailor_result.match_score,
                    "cv_path": tailor_result.pdf_path or tailor_result.cv_path,
                    "cover_letter_path": "",
                    "recording_id": recording_id,
                    "replay_used": 0,
                    "tokens_input": total_tokens_input,
                    "tokens_output": total_tokens_output,
                    "tokens_cached": total_tokens_cached,
                    "cost_usd": total_cost,
                    "duration_seconds": duration,
                    "notes": result.notes if result else None,
                },
            )

            if result is None:
                return {"status": "failed", "reason": "unknown"}
            response = result.model_dump()
            response["cv_path"] = tailor_result.pdf_path or tailor_result.cv_path
            response["cover_letter"] = cover_letter
            return response


async def run_batch(agent: JobAgent, urls: list[str], profile: dict[str, Any], concurrency: int = 2):
    sem = asyncio.Semaphore(concurrency)

    async def _run(url: str):
        async with sem:
            try:
                return await agent.process_job(url, profile)
            except Exception as exc:  # noqa: BLE001
                logger.exception("job failed: {}", exc)
                return {"status": "failed", "error": str(exc), "url": url}

    return await asyncio.gather(*[_run(url) for url in urls])
