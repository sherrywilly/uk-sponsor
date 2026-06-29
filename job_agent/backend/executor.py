from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass
from typing import Any

from playwright.async_api import Page

from .recorder import ActionRecorder


@dataclass(slots=True)
class ExecutionResult:
    status: str
    success_signal: str = ""


class ActionExecutor:
    async def execute(self, page: Page, actions: list[dict[str, Any]], cv_path: str, recorder: ActionRecorder) -> ExecutionResult:
        for action in actions:
            delay = random.uniform(0.8, 2.5)
            await asyncio.sleep(delay)
            action_type = action.get("action")
            strategy_used, selector_used = "", action.get("selector", "")
            value = action.get("value")

            if action_type == "fill":
                strategy_used = await self._fill(page, action, value)
                recorder.record("fill", strategy_used, selector_used, value, delay, page.url, "text")
            elif action_type == "select":
                strategy_used = await self._select(page, action, value)
                recorder.record("select", strategy_used, selector_used, value, delay, page.url, "select")
            elif action_type == "upload":
                strategy_used = await self._upload(page, action, cv_path)
                recorder.record("upload", strategy_used, selector_used, "cv_path", delay, page.url, "file")
            elif action_type == "click":
                strategy_used = await self._click(page, action)
                recorder.record("click", strategy_used, selector_used, None, delay, page.url, "button")

        page_text = (await page.inner_text("body")).lower()
        if "thank you for applying" in page_text or "application submitted" in page_text:
            return ExecutionResult(status="submitted", success_signal="Thank you for applying")
        if "captcha" in page_text:
            return ExecutionResult(status="captcha")
        if "next" in page_text:
            return ExecutionResult(status="next_page")
        return ExecutionResult(status="failed")

    async def _fill(self, page: Page, action: dict[str, Any], value: str | None) -> str:
        selector = action.get("selector", "")
        text = str(value or "")
        strategies = [
            ("get_by_label", lambda: page.get_by_label(selector)),
            ("get_by_placeholder", lambda: page.get_by_placeholder(selector)),
            ("css_name", lambda: page.locator(f"[name='{selector}']")),
            ("css_id", lambda: page.locator(f"#{selector}")),
            ("textbox_role", lambda: page.get_by_role("textbox", name=selector)),
        ]
        for name, factory in strategies:
            locator = factory()
            if await locator.count() > 0:
                await locator.first.click()
                await locator.first.type(text, delay=random.randint(10, 30))
                return name
        raise RuntimeError(f"Unable to fill field: {selector}")

    async def _select(self, page: Page, action: dict[str, Any], value: str | None) -> str:
        selector = action.get("selector", "")
        option = str(value or "")
        locator = page.locator(selector) if selector.startswith("#") or selector.startswith(".") else page.get_by_label(selector)
        if await locator.count() == 0:
            locator = page.locator(f"select[name='{selector}']")
        await locator.first.select_option(option)
        return "select_option"

    async def _upload(self, page: Page, action: dict[str, Any], cv_path: str) -> str:
        selector = action.get("selector", "")
        locator = page.get_by_label(selector)
        if await locator.count() == 0:
            locator = page.locator("input[type='file']")
        await locator.first.set_input_files(cv_path)
        return "file_input"

    async def _click(self, page: Page, action: dict[str, Any]) -> str:
        selector = action.get("selector", "")
        locator = page.get_by_role("button", name=selector)
        if await locator.count() == 0:
            locator = page.get_by_text(selector)
        if await locator.count() == 0:
            locator = page.locator(selector)
        await locator.first.click()
        await page.wait_for_load_state("networkidle")
        return "click"
