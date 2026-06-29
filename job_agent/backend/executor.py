from __future__ import annotations

import asyncio
import random
from typing import Any

from playwright.async_api import Page

from .recorder import ActionRecorder
from .schemas import ExecutionResult


class FormExecutor:
    async def execute(
        self,
        page: Page,
        actions: list[dict[str, Any]],
        profile: dict[str, Any],
        cv_path: str,
        recorder: ActionRecorder,
    ) -> ExecutionResult:
        for compact in actions:
            action = compact.get("a")
            strategy = compact.get("st", "get_by_label")
            selector = compact.get("s", "")
            profile_key = compact.get("v")
            delay_before = random.uniform(0.8, 2.5)
            await asyncio.sleep(delay_before)

            value = self._resolve_value(profile, profile_key, cv_path)
            page_pattern = page.url
            try:
                if action == "fill":
                    await self._try_fill(page, strategy, selector, str(value or ""))
                elif action == "select":
                    await self._try_select(page, strategy, selector, str(value or ""))
                elif action == "upload":
                    locator = self._locator(page, strategy, selector)
                    await locator.set_input_files(str(value or cv_path))
                elif action == "click":
                    locator = self._locator(page, strategy, selector)
                    await locator.click()
                    await page.wait_for_load_state("networkidle", timeout=20_000)
                else:
                    continue

                recorder.record(
                    action=action,
                    strategy=strategy,
                    selector=selector,
                    profile_key=profile_key,
                    delay_before=delay_before,
                    page_pattern=page_pattern,
                )
            except Exception as exc:  # noqa: BLE001
                return ExecutionResult(status="failed", notes=f"Action failed: {exc}")

        html = await page.content()
        text = " ".join(html.split()).lower()
        if "captcha" in text:
            return ExecutionResult(status="captcha", notes="captcha detected")
        if any(sig in text for sig in ["thank you for applying", "application submitted", "we received"]):
            return ExecutionResult(status="submitted", success_signal="submission signal detected")
        if any(sig in text for sig in ["next", "continue", "step 2"]):
            return ExecutionResult(status="next_page")

        return ExecutionResult(status="manual_review", notes="No success signal")

    async def _try_fill(self, page: Page, strategy: str, selector: str, value: str) -> None:
        candidates = [strategy, "get_by_label", "get_by_placeholder", "css"]
        for candidate in candidates:
            try:
                locator = self._locator(page, candidate, selector)
                await locator.fill("")
                await locator.type(value, delay=random.uniform(10, 30))
                return
            except Exception:  # noqa: BLE001
                continue
        raise RuntimeError(f"Unable to fill field {selector}")

    async def _try_select(self, page: Page, strategy: str, selector: str, value: str) -> None:
        locator = self._locator(page, strategy, selector)
        try:
            await locator.select_option(value=value)
        except Exception:  # noqa: BLE001
            await locator.select_option(label=value)

    def _resolve_value(self, profile: dict[str, Any], key: str | None, cv_path: str) -> Any:
        if not key:
            return None
        if key == "cv_path":
            return cv_path
        current: Any = profile
        for part in key.split("."):
            if isinstance(current, dict):
                current = current.get(part)
            else:
                return None
        return current

    def _locator(self, page: Page, strategy: str, selector: str):
        if strategy == "get_by_label":
            return page.get_by_label(selector)
        if strategy == "get_by_placeholder":
            return page.get_by_placeholder(selector)
        if strategy == "get_by_role":
            return page.get_by_role("button", name=selector)
        if strategy == "get_by_text":
            return page.get_by_text(selector)
        return page.locator(selector)
