from __future__ import annotations

import base64
import json
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from loguru import logger
from playwright.async_api import async_playwright

from .claude_client import ClaudeClient
from .config import PROFILE, SCREENSHOT_DIR, SETTINGS
from .cv_tailor import tailor_cv
from .database import Database
from .executor import ActionExecutor
from .html_extractor import extract_form_fields
from .jd_extractor import extract_jd
from .recorder import ActionRecorder, ActionReplayer, detect_ats, get_domain


@dataclass(slots=True)
class AgentResult:
    status: str
    replay_used: bool
    recording_id: int | None = None


class JobAgent:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.executor = ActionExecutor()

    async def process_job(self, job_id: int, url: str, profile: dict | None = None) -> AgentResult:
        profile = profile or PROFILE
        started = time.perf_counter()
        domain = get_domain(url)
        ats_type = detect_ats(url)

        await self.db.update_status(job_id, "running")

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=SETTINGS.playwright_headless)
            page = await browser.new_page()
            await page.goto(url, wait_until="domcontentloaded", timeout=120000)
            before_path = SCREENSHOT_DIR / f"{job_id}_before.png"
            await page.screenshot(path=str(before_path), full_page=True)

            jd = extract_jd(await page.inner_html("body"))
            if jd.sponsorship_flag == "blocked":
                await self.db.update_status(
                    job_id,
                    "skipped_no_sponsorship",
                    jd_summary=json.dumps(jd.compressed),
                    screenshot_before=str(before_path),
                )
                await browser.close()
                return AgentResult(status="skipped_no_sponsorship", replay_used=False)

            replayer = ActionReplayer(self.db)
            if await replayer.can_replay(url):
                try:
                    replay_result = await replayer.replay(page, url, profile, profile.get("cv_path", ""))
                    after_path = SCREENSHOT_DIR / f"{job_id}_after.png"
                    await page.screenshot(path=str(after_path), full_page=True)
                    await self.db.update_status(
                        job_id,
                        replay_result.status,
                        replay_used=1,
                        recording_id=replay_result.recording_id,
                        screenshot_before=str(before_path),
                        screenshot_after=str(after_path),
                        duration_seconds=time.perf_counter() - started,
                    )
                    await browser.close()
                    return AgentResult(status=replay_result.status, replay_used=True, recording_id=replay_result.recording_id)
                except Exception as exc:
                    logger.warning(f"Replay failed for job_id={job_id}: {exc}")

            claude = ClaudeClient(self.db, job_id)
            cv_path, match_score = await tailor_cv(claude, jd.compressed, domain)
            cover_letter = await claude.generate_cover_letter(domain, "Role", jd.compressed.get("tech_stack", [])[:5], profile.get("summary", ""))
            cover_letter_path = Path("cover_letters") / f"{job_id}.txt"
            (Path(__file__).resolve().parent.parent / cover_letter_path).write_text(cover_letter, encoding="utf-8")

            html = await page.inner_html("body")
            fields = extract_form_fields(html)
            recorder = ActionRecorder(self.db)
            recorder.start(domain, ats_type, urlparse(url).path)

            if fields:
                actions = await claude.extract_form_actions(fields, profile)
            else:
                screenshot = await page.screenshot(full_page=True)
                b64 = base64.b64encode(screenshot).decode("utf-8")
                actions = await claude.extract_form_actions_vision(b64, profile)

            result = await self.executor.execute(page, actions, cv_path, recorder)
            recording_id = None
            if result.status == "submitted":
                recording_id = await recorder.save(success=True, success_signal=result.success_signal)

            after_path = SCREENSHOT_DIR / f"{job_id}_after.png"
            await page.screenshot(path=str(after_path), full_page=True)

            stats = await self.db.get_stats()
            await self.db.update_status(
                job_id,
                result.status,
                jd_summary=json.dumps(jd.compressed),
                jd_keywords=json.dumps(jd.compressed.get("tech_stack", [])),
                match_score=match_score,
                cv_path=cv_path,
                cover_letter_path=str(cover_letter_path),
                recording_id=recording_id,
                replay_used=0,
                screenshot_before=str(before_path),
                screenshot_after=str(after_path),
                duration_seconds=time.perf_counter() - started,
                cost_usd=stats.get("total_cost_usd", 0),
            )
            await browser.close()
            return AgentResult(status=result.status, replay_used=False, recording_id=recording_id)
