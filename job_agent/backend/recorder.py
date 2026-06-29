from __future__ import annotations

import asyncio
import json
import random
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from playwright.async_api import Page

from .database import Database


ATS_SIGNATURES = {
    "greenhouse": ["greenhouse.io", "boards.greenhouse.io"],
    "lever": ["jobs.lever.co"],
    "workday": ["myworkdayjobs.com"],
    "ashby": ["jobs.ashbyhq.com"],
    "smartrecruiters": ["careers.smartrecruiters.com"],
    "bamboohr": ["bamboohr.com"],
}


def detect_ats(url: str) -> str:
    host = urlparse(url).netloc.lower()
    for ats, signatures in ATS_SIGNATURES.items():
        if any(sig in host for sig in signatures):
            return ats
    return "custom"


def get_domain(url: str) -> str:
    return urlparse(url).netloc.lower()


@dataclass(slots=True)
class ReplayResult:
    status: str
    steps_completed: int
    failed_step: int | None = None
    recording_id: int | None = None


class ReplayError(Exception):
    def __init__(self, step: int, message: str) -> None:
        super().__init__(message)
        self.step = step


class ActionRecorder:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.steps: list[dict[str, Any]] = []
        self.domain = ""
        self.ats_type = "custom"
        self.started_at = 0.0
        self.url_pattern = ""

    def start(self, domain: str, ats_type: str, url_pattern: str = "") -> None:
        self.steps = []
        self.domain = domain
        self.ats_type = ats_type
        self.url_pattern = url_pattern
        self.started_at = time.perf_counter()

    def record(
        self,
        action: str,
        strategy: str,
        selector: str,
        profile_key: str | None,
        delay_before: float,
        page_pattern: str,
        field_type: str | None = None,
    ) -> None:
        self.steps.append(
            {
                "step": len(self.steps) + 1,
                "page_pattern": page_pattern,
                "action": action,
                "strategy": strategy,
                "selector": selector,
                "field_type": field_type,
                "profile_key": profile_key,
                "delay_before": delay_before,
            }
        )

    def record_page_transition(self, old_url: str, new_url: str) -> None:
        self.steps.append(
            {
                "step": len(self.steps) + 1,
                "action": "navigate",
                "strategy": "url_change",
                "selector": f"{old_url} -> {new_url}",
                "profile_key": None,
                "delay_before": 0,
                "page_pattern": new_url,
            }
        )

    async def save(self, success: bool, success_signal: str) -> int | None:
        if not success or not self.steps:
            return None
        elapsed = time.perf_counter() - self.started_at
        payload = {
            "domain": self.domain,
            "ats_type": self.ats_type,
            "recorded_at": time.strftime("%Y-%m-%d"),
            "success": success,
            "steps": self.steps,
            "success_signal": success_signal,
            "total_pages": len({s["page_pattern"] for s in self.steps if s.get("page_pattern")}),
        }
        return await self.db.upsert_recording(
            domain=self.domain,
            ats_type=self.ats_type,
            url_pattern=self.url_pattern,
            script_json=payload,
            completion_seconds=elapsed,
        )


class ActionReplayer:
    def __init__(self, db: Database) -> None:
        self.db = db

    async def _get_recording(self, url: str) -> dict[str, Any] | None:
        domain = get_domain(url)
        ats_type = detect_ats(url)
        by_ats = None
        if ats_type != "custom":
            by_ats = await self.db.get_recording_by_ats(ats_type)
        return by_ats or await self.db.get_recording_by_domain(domain)

    async def can_replay(self, url: str) -> bool:
        recording = await self._get_recording(url)
        return bool(recording)

    async def replay(self, page: Page, url: str, profile: dict[str, Any], cv_path: str) -> ReplayResult:
        recording = await self._get_recording(url)
        if not recording:
            return ReplayResult(status="missing", steps_completed=0)

        script = json.loads(recording["script_json"])
        steps = script.get("steps", [])

        for index, step in enumerate(steps, start=1):
            try:
                await self._run_step(page, step, profile, cv_path)
            except Exception as exc:
                await self.handle_replay_failure(exc, int(recording["id"]))
                raise ReplayError(index, str(exc)) from exc

        await self.db.increment_recording_success(int(recording["id"]))
        return ReplayResult(status="submitted", steps_completed=len(steps), recording_id=int(recording["id"]))

    async def _run_step(self, page: Page, step: dict[str, Any], profile: dict[str, Any], cv_path: str) -> None:
        action = step.get("action")
        selector = step.get("selector")
        strategy = step.get("strategy")
        profile_key = step.get("profile_key")
        delay = float(step.get("delay_before") or 0)

        jitter = delay * random.uniform(0.8, 1.2)
        if jitter > 0:
            await asyncio.sleep(jitter)

        value = self._resolve_profile(profile, profile_key)
        if profile_key == "cv_path":
            value = cv_path

        if action == "fill":
            locator = self._get_locator(page, strategy, selector)
            await locator.fill(str(value or ""))
        elif action == "upload":
            locator = self._get_locator(page, strategy, selector)
            await locator.set_input_files(str(value or cv_path))
        elif action == "select":
            locator = self._get_locator(page, strategy, selector)
            await locator.select_option(str(value or ""))
        elif action == "click":
            locator = self._get_locator(page, strategy, selector)
            await locator.click()
            await page.wait_for_load_state("networkidle")
        elif action == "navigate":
            return

    def _get_locator(self, page: Page, strategy: str, selector: str):
        if strategy == "get_by_label":
            return page.get_by_label(selector)
        if strategy == "get_by_placeholder":
            return page.get_by_placeholder(selector)
        if strategy == "get_by_role":
            return page.get_by_role("button", name=selector)
        if strategy == "css":
            return page.locator(selector)
        return page.get_by_text(selector)

    def _resolve_profile(self, profile: dict[str, Any], key: str | None) -> Any:
        if not key:
            return None
        current: Any = profile
        for part in key.split("."):
            if isinstance(current, dict):
                current = current.get(part)
            else:
                return None
        return current

    async def handle_replay_failure(self, error: Exception, recording_id: int) -> None:
        _ = error
        await self.db.increment_recording_fail(recording_id)
