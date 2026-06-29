from __future__ import annotations

import asyncio
import json
import random
import time
from datetime import datetime
from typing import Any

from playwright.async_api import Page

from .ats import detect_ats_type, domain_from_url
from .database import Database
from .schemas import ActionStep, RecordingScript, ReplayResult


class ReplayError(Exception):
    def __init__(self, step: int, message: str) -> None:
        self.step = step
        super().__init__(message)


class ActionRecorder:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.domain = ""
        self.ats_type = "custom"
        self.steps: list[ActionStep] = []
        self.start_at = 0.0
        self.page_transitions = 0

    def start(self, domain: str, ats_type: str) -> None:
        self.domain = domain
        self.ats_type = ats_type
        self.steps = []
        self.start_at = time.monotonic()
        self.page_transitions = 0

    def record(
        self,
        *,
        action: str,
        strategy: str,
        selector: str,
        profile_key: str | None,
        delay_before: float,
        page_pattern: str | None,
        field_type: str | None = None,
    ) -> None:
        self.steps.append(
            ActionStep(
                step=len(self.steps) + 1,
                action=action,
                strategy=strategy,
                selector=selector,
                profile_key=profile_key,
                delay_before=delay_before,
                page_pattern=page_pattern,
                field_type=field_type,
            )
        )

    def record_page_transition(self, old_url: str, new_url: str) -> None:
        self.page_transitions += 1
        self.record(
            action="navigate",
            strategy="url_change",
            selector=f"{old_url} -> {new_url}",
            profile_key=None,
            delay_before=0,
            page_pattern=new_url,
        )

    async def save(self, success: bool, success_signal: str | None) -> int:
        elapsed = max(0.1, time.monotonic() - self.start_at)
        script = RecordingScript(
            domain=self.domain,
            ats_type=self.ats_type,
            recorded_at=datetime.utcnow().date().isoformat(),
            success=success,
            steps=self.steps,
            success_signal=success_signal,
            total_pages=max(1, self.page_transitions + 1),
        ).model_dump()

        recording_id = await self.db.upsert_recording(
            domain=self.domain,
            ats_type=self.ats_type,
            url_pattern=self.domain,
            script_json=script,
            avg_completion_time=elapsed,
            notes="auto-generated",
        )
        return recording_id


class ActionReplayer:
    def __init__(self, db: Database) -> None:
        self.db = db

    async def _load_script(self, url: str) -> tuple[int, dict[str, Any]] | None:
        domain = domain_from_url(url)
        ats_type = detect_ats_type(url)
        row = None
        if ats_type != "custom":
            row = await self.db.get_recording_by_ats(ats_type)
        if not row:
            row = await self.db.get_recording_by_domain(domain)
        if not row:
            return None
        return row["id"], json.loads(row["script_json"])

    async def can_replay(self, url: str) -> bool:
        loaded = await self._load_script(url)
        return loaded is not None

    async def replay(
        self,
        page: Page,
        url: str,
        profile: dict[str, Any],
        cv_path: str,
    ) -> ReplayResult:
        loaded = await self._load_script(url)
        if not loaded:
            return ReplayResult(status="no_recording", steps_completed=0)

        recording_id, script = loaded
        steps = script.get("steps", [])

        try:
            for idx, step in enumerate(steps, start=1):
                await self._run_step(page, step, profile, cv_path)
                await asyncio.sleep(self._jitter(step.get("delay_before", 0)))
            await self.db.increment_success(recording_id)
            return ReplayResult(status="submitted", steps_completed=len(steps), recording_id=recording_id)
        except ReplayError as exc:
            await self.handle_replay_failure(exc, recording_id)
            return ReplayResult(
                status="failed",
                steps_completed=max(0, exc.step - 1),
                failed_step=exc.step,
                recording_id=recording_id,
            )

    async def _run_step(self, page: Page, step: dict[str, Any], profile: dict[str, Any], cv_path: str) -> None:
        action = step.get("action")
        strategy = step.get("strategy")
        selector = step.get("selector")
        value = self._profile_value(profile, step.get("profile_key"))
        if step.get("profile_key") == "cv_path":
            value = cv_path

        try:
            if action == "fill":
                await self._perform_fill(page, strategy, selector, str(value or ""))
            elif action == "upload":
                locator = self._locator(page, strategy, selector)
                await locator.set_input_files(str(value or cv_path))
            elif action == "select":
                locator = self._locator(page, strategy, selector)
                await locator.select_option(str(value or ""))
            elif action == "click":
                locator = self._locator(page, strategy, selector)
                await locator.click()
                await page.wait_for_load_state("networkidle", timeout=15_000)
            elif action == "navigate":
                return
            else:
                raise ReplayError(int(step.get("step") or 0), f"unknown action {action}")
        except Exception as exc:  # noqa: BLE001
            raise ReplayError(int(step.get("step") or 0), str(exc)) from exc

    async def _perform_fill(self, page: Page, strategy: str, selector: str, value: str) -> None:
        locator = self._locator(page, strategy, selector)
        await locator.fill("")
        await locator.type(value, delay=random.uniform(10, 30))

    def _locator(self, page: Page, strategy: str, selector: str):
        if strategy == "get_by_label":
            return page.get_by_label(selector)
        if strategy == "get_by_placeholder":
            return page.get_by_placeholder(selector)
        if strategy == "get_by_role":
            return page.get_by_role("button", name=selector)
        if strategy == "css":
            return page.locator(selector)
        if strategy == "get_by_text":
            return page.get_by_text(selector)
        return page.locator(selector)

    def _profile_value(self, profile: dict[str, Any], key: str | None) -> Any:
        if not key:
            return None
        current: Any = profile
        for part in key.split("."):
            if isinstance(current, dict):
                current = current.get(part)
            else:
                return None
        return current

    def _jitter(self, delay: float) -> float:
        if delay <= 0:
            return random.uniform(0.2, 0.8)
        return max(0.2, delay * random.uniform(0.8, 1.2))

    async def handle_replay_failure(self, error: ReplayError, recording_id: int) -> None:
        _ = error
        await self.db.increment_fail(recording_id)
