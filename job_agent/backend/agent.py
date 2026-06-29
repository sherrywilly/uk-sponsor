from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from playwright.async_api import async_playwright

from .claude_client import ClaudeClient
from .config import SCREENSHOT_DIR, SETTINGS
from .cv_tailor import tailor_cv
from .database import Database
from .executor import ActionExecutor
from .html_extractor import extract_form_fields
from .jd_extractor import extract_jd_from_html
from .recorder import ActionRecorder, ActionReplayer, detect_ats, domain_from_url


@dataclass(slots=True)
class AgentResult:
    status: str
    replay_used: bool
    recording_id: int | None = None
    match_score: float = 0
    cv_path: str = ""
    cover_letter: str = ""
    notes: str = ""


class JobAgent:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.claude = ClaudeClient(
            api_key=SETTINGS.anthropic_api_key,
            model_haiku=SETTINGS.model_haiku,
            model_sonnet=SETTINGS.model_sonnet,
            db=db,
        )
        self.executor = ActionExecutor()

    async def process_job(self, url: str, profile: dict[str, Any] | None = None, job_id: int | None = None) -> AgentResult:
        profile = profile or SETTINGS.profile
        domain = domain_from_url(url)
        ats_type = detect_ats(url)

        await self.db.insert_job(
            {
                "url": url,
                "domain": domain,
                "company": domain,
                "job_title": "",
                "ats_type": ats_type,
                "status": "running",
            }
        )

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context()
            page = await context.new_page()
            await page.goto(url, wait_until="domcontentloaded")

            screenshot_before = SCREENSHOT_DIR / "before.png"
            await page.screenshot(path=str(screenshot_before), full_page=True)

            jd = extract_jd_from_html(await page.content())
            if jd.sponsorship_flag == "blocked":
                await self.db.update_job(url, status="no_sponsorship", jd_summary=str(jd.compressed))
                await browser.close()
                return AgentResult(status="no_sponsorship", replay_used=False)

            replayer = ActionReplayer(self.db)
            if await replayer.can_replay(url):
                try:
                    replay = await replayer.replay(page, url, profile, str(SETTINGS.base_cv_path))
                    await self.db.update_job(
                        url,
                        status=replay.status,
                        replay_used=1,
                        recording_id=replay.recording_id,
                        screenshot_before=str(screenshot_before),
                    )
                    await browser.close()
                    return AgentResult(status=replay.status, replay_used=True, recording_id=replay.recording_id)
                except Exception:  # noqa: BLE001
                    pass

            cv_path, match_score = await tailor_cv(
                claude=self.claude,
                base_cv_path=SETTINGS.base_cv_path,
                base_cv_text=SETTINGS.base_cv_text,
                compressed_jd=jd.compressed,
                company=domain,
                job_id=job_id,
            )
            cover_letter = await self.claude.generate_cover_letter(
                company=domain,
                role="Software Engineer",
                jd_keywords=jd.compressed.get("tech_stack", []),
                profile_summary=profile.get("summary", "Experienced engineer."),
                job_id=job_id,
            )

            html = await page.inner_html("body")
            fields = extract_form_fields(html)

            recorder = ActionRecorder(self.db)
            recorder.start(domain, ats_type)

            if fields:
                actions = await self.claude.extract_form_actions(fields, profile, job_id=job_id)
            else:
                screenshot = await page.screenshot(full_page=True)
                actions = await self.claude.extract_form_actions_vision(screenshot, profile, job_id=job_id)

            page_num = 0
            result = None
            old_url = page.url
            while page_num < 10:
                result = await self.executor.execute(page, actions, cv_path, recorder, SCREENSHOT_DIR)
                if result.status in {"submitted", "failed", "captcha"}:
                    break
                if result.status == "next_page":
                    recorder.record_page_transition(old_url, page.url)
                    old_url = page.url
                    html = await page.inner_html("body")
                    fields = extract_form_fields(html)
                    if not fields:
                        break
                    actions = await self.claude.extract_form_actions(fields, profile, job_id=job_id)
                    page_num += 1
                await asyncio.sleep(0)

            recording_id = None
            status = result.status if result else "failed"
            if status == "submitted":
                recording_id = await recorder.save(success=True, success_signal=result.success_signal, url_pattern=domain)

            await self.db.update_job(
                url,
                status=status,
                jd_summary=str(jd.compressed),
                jd_keywords=",".join(jd.compressed.get("tech_stack", [])),
                match_score=match_score,
                cv_path=cv_path,
                cover_letter_path="",
                recording_id=recording_id,
                replay_used=0,
                screenshot_before=str(screenshot_before),
                screenshot_after=str(SCREENSHOT_DIR / "after_submit.png"),
            )

            await browser.close()
            return AgentResult(
                status=status,
                replay_used=False,
                recording_id=recording_id,
                match_score=match_score,
                cv_path=cv_path,
                cover_letter=cover_letter,
            )
