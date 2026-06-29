from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .recorder import ActionRecorder


@dataclass(slots=True)
class ExecutionResult:
    status: str
    success_signal: str = ""


class ActionExecutor:
    async def execute(
        self,
        page: Any,
        actions: list[dict[str, Any]],
        cv_path: str,
        recorder: ActionRecorder,
        screenshot_dir: Path,
    ) -> ExecutionResult:
        for action in actions:
            delay_before = random.uniform(0.8, 2.5)
            await asyncio.sleep(delay_before)

            act = action.get("action", "fill")
            strategy = action.get("strategy", "css")
            selector = action.get("selector", "")
            value_key = action.get("value", "")

            if act == "fill":
                locator, used_strategy = await self._find_fill_locator(page, selector, strategy)
                value = self._value_from_profile_key(value_key)
                await locator.type(str(value), delay=random.randint(10, 30))
                recorder.record(
                    action="fill",
                    strategy=used_strategy,
                    selector=selector,
                    profile_key=value_key,
                    delay_before=delay_before,
                    page_pattern=page.url,
                    field_type="text",
                )
            elif act == "select":
                locator = await self._resolve(page, strategy, selector)
                await locator.select_option(str(self._value_from_profile_key(value_key)))
                recorder.record(
                    action="select",
                    strategy=strategy,
                    selector=selector,
                    profile_key=value_key,
                    delay_before=delay_before,
                    page_pattern=page.url,
                )
            elif act == "upload":
                locator = await self._resolve(page, strategy, selector)
                await locator.set_input_files(cv_path)
                recorder.record(
                    action="upload",
                    strategy=strategy,
                    selector=selector,
                    profile_key="cv_path",
                    delay_before=delay_before,
                    page_pattern=page.url,
                )
            elif act == "click":
                locator = await self._resolve(page, strategy, selector)
                await locator.click()
                await page.wait_for_load_state("networkidle")
                recorder.record(
                    action="click",
                    strategy=strategy,
                    selector=selector,
                    profile_key="",
                    delay_before=delay_before,
                    page_pattern=page.url,
                )

        content = (await page.content()).lower()
        after_path = screenshot_dir / "after_submit.png"
        await page.screenshot(path=str(after_path), full_page=True)
        if "captcha" in content:
            return ExecutionResult(status="captcha")
        if any(sig in content for sig in ("thank you for applying", "application submitted", "we received your application")):
            return ExecutionResult(status="submitted", success_signal="Thank you for applying")
        if "next" in content and "page" in content:
            return ExecutionResult(status="next_page")
        return ExecutionResult(status="failed")

    async def _find_fill_locator(self, page: Any, selector: str, strategy: str) -> tuple[Any, str]:
        ordered = [strategy, "get_by_label", "get_by_placeholder", "css", "get_by_role"]
        seen: set[str] = set()
        for strat in ordered:
            if strat in seen:
                continue
            seen.add(strat)
            try:
                locator = await self._resolve(page, strat, selector)
                await locator.first.wait_for(timeout=1000)
                return locator.first, strat
            except Exception:  # noqa: BLE001
                continue
        return page.locator(selector), "css"

    async def _resolve(self, page: Any, strategy: str, selector: str) -> Any:
        if strategy == "get_by_label":
            return page.get_by_label(selector)
        if strategy == "get_by_placeholder":
            return page.get_by_placeholder(selector)
        if strategy == "get_by_role":
            return page.get_by_role("button", name=selector)
        if strategy == "css":
            return page.locator(selector)
        return page.locator(selector)

    @staticmethod
    def _value_from_profile_key(key: str) -> str:
        defaults = {
            "name.first": "First",
            "name.last": "Last",
            "email": "candidate@example.com",
            "phone": "+440000000000",
            "cv_path": "",
            "location": "United Kingdom",
        }
        return defaults.get(key, key)
