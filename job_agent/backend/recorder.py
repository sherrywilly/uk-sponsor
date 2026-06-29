from __future__ import annotations

import asyncio
import json
import random
import time
from dataclasses import dataclass
from datetime import date
from typing import Any
from urllib.parse import urlparse

from .database import Database

ATS_PATTERNS = {
    "greenhouse": ("greenhouse.io", "boards.greenhouse.io"),
    "lever": ("jobs.lever.co",),
    "workday": ("myworkdayjobs.com",),
    "ashby": ("jobs.ashbyhq.com",),
    "smartrecruiters": ("careers.smartrecruiters.com",),
    "bamboohr": ("bamboohr.com",),
}


def detect_ats(url: str) -> str:
    host = urlparse(url).netloc.lower()
    for ats, patterns in ATS_PATTERNS.items():
        if any(p in host for p in patterns):
            return ats
    return "custom"


def domain_from_url(url: str) -> str:
    return urlparse(url).netloc.lower()


@dataclass(slots=True)
class ReplayResult:
    status: str
    steps_completed: int
    failed_step: int | None = None
    recording_id: int | None = None


class ReplayError(RuntimeError):
    def __init__(self, message: str, step: int | None = None) -> None:
        super().__init__(message)
        self.step = step


class ActionRecorder:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.domain = ""
        self.ats_type = "custom"
        self.steps: list[dict[str, Any]] = []
        self.started_at = 0.0

    def start(self, domain: str, ats_type: str) -> None:
        self.domain = domain
        self.ats_type = ats_type
        self.steps = []
        self.started_at = time.monotonic()

    def record(
        self,
        *,
        action: str,
        strategy: str,
        selector: str,
        profile_key: str,
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
                "delay_before": round(delay_before, 3),
            }
        )

    def record_page_transition(self, old_url: str, new_url: str) -> None:
        self.steps.append(
            {
                "step": len(self.steps) + 1,
                "action": "navigate",
                "old_url": old_url,
                "new_url": new_url,
                "delay_before": 0,
            }
        )

    async def save(self, *, success: bool, success_signal: str, url_pattern: str = "") -> int:
        elapsed = max(time.monotonic() - self.started_at, 0.0)
        script = {
            "domain": self.domain,
            "ats_type": self.ats_type,
            "recorded_at": str(date.today()),
            "success": success,
            "steps": self.steps,
            "success_signal": success_signal,
            "total_pages": len([s for s in self.steps if s.get("action") == "navigate"]) + 1,
        }

        rec_id = await self.db.upsert_recording(
            domain=self.domain,
            ats_type=self.ats_type,
            url_pattern=url_pattern,
            script_json=script,
            completion_time=elapsed,
        )
        if success:
            await self.db.increment_recording_success(rec_id, elapsed)
        return rec_id


class ActionReplayer:
    def __init__(self, db: Database) -> None:
        self.db = db

    async def _lookup_recording(self, url: str) -> dict[str, Any] | None:
        ats_type = detect_ats(url)
        domain = domain_from_url(url)
        if ats_type != "custom":
            rec = await self.db.get_recording_by_ats(ats_type)
            if rec:
                return rec
        return await self.db.get_recording_by_domain(domain)

    async def can_replay(self, url: str) -> bool:
        return (await self._lookup_recording(url)) is not None

    async def replay(self, page: Any, url: str, profile: dict[str, Any], cv_path: str) -> ReplayResult:
        rec = await self._lookup_recording(url)
        if not rec:
            return ReplayResult(status="unavailable", steps_completed=0)

        script = json.loads(rec["script_json"])
        steps: list[dict[str, Any]] = script.get("steps", [])

        completed = 0
        for step in steps:
            action = step.get("action")
            delay_before = float(step.get("delay_before", 0))
            await asyncio.sleep(max(0.05, delay_before * random.uniform(0.8, 1.2)))
            try:
                if action == "fill":
                    await self._do_fill(page, step, profile)
                elif action == "upload":
                    await self._do_upload(page, step, profile, cv_path)
                elif action == "select":
                    await self._do_select(page, step, profile)
                elif action == "click":
                    await self._do_click(page, step)
                elif action == "navigate":
                    continue
                else:
                    raise ReplayError(f"Unsupported replay action: {action}", step.get("step"))
            except Exception as exc:  # noqa: BLE001
                await self.handle_replay_failure(exc, rec["id"])
                raise ReplayError(str(exc), step.get("step")) from exc
            completed += 1

        await self.db.increment_recording_success(rec["id"])
        return ReplayResult(
            status="submitted",
            steps_completed=completed,
            recording_id=rec["id"],
        )

    async def handle_replay_failure(self, error: Exception, recording_id: int) -> None:
        _ = error
        await self.db.increment_recording_fail(recording_id)

    async def _resolve_locator(self, page: Any, strategy: str, selector: str) -> Any:
        if strategy == "get_by_label":
            return page.get_by_label(selector)
        if strategy == "get_by_placeholder":
            return page.get_by_placeholder(selector)
        if strategy == "get_by_role":
            return page.get_by_role("button", name=selector)
        if strategy == "css":
            return page.locator(selector)
        return page.locator(selector)

    async def _do_fill(self, page: Any, step: dict[str, Any], profile: dict[str, Any]) -> None:
        locator = await self._resolve_locator(page, step.get("strategy", "css"), step.get("selector", ""))
        value = _profile_value(profile, step.get("profile_key", ""))
        await locator.fill(str(value))

    async def _do_select(self, page: Any, step: dict[str, Any], profile: dict[str, Any]) -> None:
        locator = await self._resolve_locator(page, step.get("strategy", "css"), step.get("selector", ""))
        value = _profile_value(profile, step.get("profile_key", ""))
        await locator.select_option(str(value))

    async def _do_upload(self, page: Any, step: dict[str, Any], profile: dict[str, Any], cv_path: str) -> None:
        locator = await self._resolve_locator(page, step.get("strategy", "css"), step.get("selector", ""))
        upload_path = _profile_value(profile, step.get("profile_key", "")) or cv_path
        await locator.set_input_files(str(upload_path))

    async def _do_click(self, page: Any, step: dict[str, Any]) -> None:
        locator = await self._resolve_locator(page, step.get("strategy", "css"), step.get("selector", ""))
        await locator.click()
        await page.wait_for_load_state("networkidle")


def _profile_value(profile: dict[str, Any], key: str) -> Any:
    if not key:
        return ""
    current: Any = profile
    for part in key.split("."):
        if isinstance(current, dict):
            current = current.get(part)
        else:
            return ""
    return current if current is not None else ""
