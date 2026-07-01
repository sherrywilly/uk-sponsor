"""
browser_agent.py — Generic observe → reason → act browser agent.

This is the core of Phase 2.  The agent has NO knowledge of careers pages,
job scraping, or any domain.  It accepts a free-text task description and
autonomously drives the browser to complete it using the tool catalogue
defined in tools.py.

Loop
----
For each iteration the agent:
  1. Observes — collects current URL, page title, visible text, interactive
     elements, and a summary of recent browser history.
  2. Reasons — sends the observation to the LLM which returns a structured
     JSON response containing: reasoning, tool name, arguments, and expected
     outcome.
  3. Acts — the ToolExecutor executes the chosen tool and returns a result.
  4. Logs — every step is appended to a JSON action log persisted to disk
     for replay and debugging.
  5. Terminates — when the LLM calls `done` or `give_up`, or when the
     maximum number of iterations is reached.

Special handling
----------------
* Popups / cookie banners — proactively dismissed at the start of each page load.
* Infinite scroll — the LLM can call scroll("down") or scroll("bottom").
* Pagination — handled transparently; the LLM calls goto() or click() on
  next-page links.
* Dynamic JS — Playwright waits for networkidle after each navigation.
* Retries — tool failures are retried up to MAX_RETRIES times; a screenshot
  is taken automatically on failure.
* Multiple tabs — new pages opened by the browser are detected and brought
  into focus.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger

from agent import AIAgent
from browser import BrowserManager
from tools import Tool, ToolExecutor, tool_catalogue_text

_OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", "output"))
_MAX_ITERATIONS: int = 40
_MAX_RETRIES: int = 3


class BrowserAgent:
    """
    Generic LLM-driven browser agent.

    Usage::

        agent_llm = AIAgent()
        async with browser_session() as bm:
            agent = BrowserAgent(browser=bm, agent=agent_llm)
            result = await agent.run("Find all job openings at https://example.com")
    """

    def __init__(
        self,
        browser: BrowserManager,
        agent: AIAgent,
        max_iterations: int = _MAX_ITERATIONS,
    ) -> None:
        self._browser = browser
        self._agent = agent
        self._executor = ToolExecutor(browser)
        self._max_iterations = max_iterations
        self._action_log: list[dict] = []
        self._history: list[str] = []   # short human-readable summary of past actions

    # ── Public API ────────────────────────────────────────────────────────────

    async def run(self, task: str) -> Any:
        """
        Execute *task* autonomously.

        Returns the value passed to the `done` tool, or None on failure.
        """
        logger.info("BrowserAgent starting task: {}", task)
        self._action_log = []
        self._history = []

        for iteration in range(1, self._max_iterations + 1):
            logger.info("─── Iteration {}/{} ───", iteration, self._max_iterations)

            # ── 1. Observe ────────────────────────────────────────────────
            observation = await self._observe()

            # ── 2. Reason ─────────────────────────────────────────────────
            decision = await self._agent.decide_action(
                task=task,
                observation=observation,
                history=self._history,
                iteration=iteration,
            )

            tool_name = decision.get("tool", Tool.GIVE_UP)
            tool_args = decision.get("args", {})
            reasoning = decision.get("reasoning", "")
            expected = decision.get("expected_outcome", "")

            logger.info("AI reasoning: {}", reasoning)
            logger.info("AI chose tool: {}  args: {}", tool_name, tool_args)

            # ── 3. Terminal signals ───────────────────────────────────────
            if tool_name == Tool.DONE:
                result = tool_args.get("result") or expected
                logger.success("Task complete. Result: {}", str(result)[:200])
                self._log_action(iteration, observation, decision, {"done": result})
                self._save_action_log()
                return result

            if tool_name == Tool.GIVE_UP:
                reason = tool_args.get("reason", "No reason given")
                logger.warning("Agent gave up: {}", reason)
                self._log_action(iteration, observation, decision, {"gave_up": reason})
                self._save_action_log()
                return None

            # ── 4. Act (with retry) ───────────────────────────────────────
            tool_result = None
            for attempt in range(1, _MAX_RETRIES + 1):
                tool_result = await self._executor.execute(tool_name, tool_args)
                if tool_result.success:
                    break
                logger.warning(
                    "Tool {} failed (attempt {}/{}): {}",
                    tool_name, attempt, _MAX_RETRIES, tool_result.error,
                )
                if attempt < _MAX_RETRIES:
                    await self._browser.page.wait_for_timeout(1000 * attempt)

            # ── 5. Handle new tabs / popups opened by the browser ─────────
            await self._focus_latest_page()

            # ── 6. Proactively dismiss cookie banners after navigation ─────
            if tool_name == Tool.GOTO:
                await self._executor.execute(Tool.DISMISS_POPUP, {})

            # ── 7. Log ────────────────────────────────────────────────────
            history_entry = (
                f"[{iteration}] {tool_name}({_fmt_args_short(tool_args)}) → "
                f"{'OK' if tool_result and tool_result.success else 'FAIL'}"
            )
            self._history.append(history_entry)
            if len(self._history) > 20:
                self._history = self._history[-20:]

            self._log_action(
                iteration,
                observation,
                decision,
                tool_result.to_dict() if tool_result else {},
            )

        logger.error("Reached max iterations ({}) without completing task.", self._max_iterations)
        self._save_action_log()
        return None

    # ── Observation ───────────────────────────────────────────────────────────

    async def _observe(self) -> dict:
        """Collect the current page state and return it as a structured dict."""
        try:
            current_url = await self._browser.get_current_url()
            title = await self._browser.page.title()
            page_text = await self._browser.get_page_text()
            elements = await self._browser.get_interactive_elements()
        except Exception as exc:
            logger.warning("Observation error: {}", exc)
            return {"error": str(exc)}

        return {
            "current_url": current_url,
            "page_title": title,
            "page_text_snippet": page_text[:3000],
            "interactive_elements": elements[:80],
        }

    # ── Helpers ───────────────────────────────────────────────────────────────

    async def _focus_latest_page(self) -> None:
        """
        If the browser has opened a new tab/page, bring it into focus so that
        subsequent observations and actions apply to the newest page.
        """
        try:
            context = self._browser._context
            if context is None:
                return
            pages = context.pages
            if len(pages) > 1:
                latest = pages[-1]
                if not latest.is_closed():
                    await latest.bring_to_front()
                    self._browser._page = latest
                    logger.info("Switched to new tab: {}", latest.url)
        except Exception:
            pass

    def _log_action(
        self,
        iteration: int,
        observation: dict,
        decision: dict,
        result: dict,
    ) -> None:
        """Append one step to the in-memory action log."""
        self._action_log.append(
            {
                "iteration": iteration,
                "timestamp": datetime.now().isoformat(),
                "observation": {
                    "current_url": observation.get("current_url"),
                    "page_title": observation.get("page_title"),
                    "page_text_snippet": (
                        observation.get("page_text_snippet", "")[:500]
                    ),
                },
                "decision": decision,
                "result": result,
            }
        )

    def _save_action_log(self) -> None:
        """Persist the action log to output/action_log_<timestamp>.json."""
        _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = _OUTPUT_DIR / f"action_log_{ts}.json"
        try:
            path.write_text(
                json.dumps(self._action_log, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            logger.info("Action log saved: {}", path)
        except Exception as exc:
            logger.warning("Could not save action log: {}", exc)

    @property
    def action_log(self) -> list[dict]:
        """Read-only view of the accumulated action log."""
        return list(self._action_log)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _fmt_args_short(args: dict) -> str:
    """Very compact arg summary for history lines."""
    parts = []
    for k, v in args.items():
        if isinstance(v, str):
            v = v[:40] + ("…" if len(v) > 40 else "")
        elif isinstance(v, list):
            v = f"[{len(v)}]"
        parts.append(f"{k}={v!r}")
    return ", ".join(parts)
