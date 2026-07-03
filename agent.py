"""
agent.py — LLM-powered reasoning layer.

Supports OpenAI, Anthropic, and OpenRouter as providers (selected via the
AI_PROVIDER environment variable).

Phase 2: the agent is fully generic — it has no knowledge of careers pages,
job scraping, or any other domain.  It exposes a single public method,
decide_action(), which receives a structured observation of the current browser
state and returns a tool-call decision.

The domain-specific prompts (career finder, job extractor) now live in
career_finder.py and job_scraper.py respectively, so this file remains a
reusable reasoning primitive.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any

from dotenv import load_dotenv
from loguru import logger

load_dotenv()

# ── Provider selection ────────────────────────────────────────────────────────

AI_PROVIDER: str = os.getenv("AI_PROVIDER", "openrouter").lower()
OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o")
ANTHROPIC_MODEL: str = os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-20241022")
OPENROUTER_MODEL: str = os.getenv("OPENROUTER_MODEL", "openai/gpt-4o")
OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"


def _get_openai_client():  # type: ignore[return]
    try:
        from openai import AsyncOpenAI  # type: ignore

        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY is not set.")
        return AsyncOpenAI(api_key=api_key)
    except ImportError as exc:
        raise ImportError("Install the openai package: pip install openai") from exc


def _get_anthropic_client():  # type: ignore[return]
    try:
        from anthropic import AsyncAnthropic  # type: ignore

        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY is not set.")
        return AsyncAnthropic(api_key=api_key)
    except ImportError as exc:
        raise ImportError(
            "Install the anthropic package: pip install anthropic"
        ) from exc


def _get_openrouter_client():  # type: ignore[return]
    try:
        from openai import AsyncOpenAI  # type: ignore

        api_key = os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            raise ValueError("OPENROUTER_API_KEY is not set.")
        return AsyncOpenAI(api_key=api_key, base_url=OPENROUTER_BASE_URL)
    except ImportError as exc:
        raise ImportError("Install the openai package: pip install openai") from exc


# ── System prompt ─────────────────────────────────────────────────────────────

def _build_system_prompt(tool_catalogue: str) -> str:
    return f"""
You are a browser-automation AI agent.
Your job is to complete the user task by choosing exactly one tool call per turn.

{tool_catalogue}

You will receive this observation each turn:
- task: overall goal
- iteration: current step number
- current_url: URL of the active tab
- page_title: current page title
- page_text: visible text snippet (truncated)
- page_html: raw HTML snippet (truncated)
- elements: visible interactive elements
- history: recent actions and outcomes

Response format requirements:
- Return JSON only. Do not use markdown fences.
- Return exactly one object with these keys:
{{
    "reasoning": "<brief rationale for the next action>",
  "tool": "<tool name from the catalogue>",
    "args": {{ <tool arguments as a JSON object> }},
  "expected_outcome": "<one sentence describing what you expect to happen>"
}}

Decision policy:
- Choose exactly one tool per response.
- Prefer click(text=...) on visible labels before CSS selectors.
- Use goto(url=...) only for URLs already observed in page content, elements, or history.
- Prefer public listing/content pages over personalised pages such as saved, favourites,
  account, login, or register routes unless the task explicitly asks for them.
- If a popup or cookie banner blocks interaction, call dismiss_popup() first.
- If an action fails, try a different strategy instead of repeating the same failing call.

Completion rules:
- Call done(result=...) only when the task goal has been achieved.
- Use result to include the final answer, usually the current URL or requested value.
- Call give_up(reason=...) only after multiple reasonable attempts have failed.

Safety and quality rules:
- Do not invent facts, page content, or unseen URLs.
- Keep args minimal and valid for the selected tool.
- expected_outcome must be specific and testable on the next observation.
""".strip()


# ── Core agent class ──────────────────────────────────────────────────────────


class AIAgent:
    """
    Generic LLM reasoning layer.

    The only public method is decide_action(), which accepts a structured
    browser observation and returns a tool-call decision.

    For domain-specific extraction tasks (job details, link lists) callers
    should use call_with_prompt() directly with their own system and user
    prompts.
    """

    def __init__(self) -> None:
        self._provider = AI_PROVIDER
        logger.info("AI agent initialised with provider: {}", self._provider)
        # Import here to avoid circular import at module load time
        from tools import tool_catalogue_text
        self._system_prompt = _build_system_prompt(tool_catalogue_text())

    # ── Public API ────────────────────────────────────────────────────────────

    async def decide_action(
        self,
        task: str,
        observation: dict,
        history: list[str],
        iteration: int,
    ) -> dict[str, Any]:
        """
        Given the current browser state, decide the next tool to call.

        Returns a dict with keys: reasoning, tool, args, expected_outcome.
        """
        elements_summary = "\n".join(
            f"  [{i}] {el['tag'].upper()} | text='{el['text']}'"
            + (f" | href='{el['href']}'" if el.get("href") else "")
            for i, el in enumerate(observation.get("interactive_elements", [])[:80])
        )

        history_text = (
            "\n".join(f"  {h}" for h in history[-15:]) if history else "  (none yet)"
        )

        user_prompt = (
            f"task: {task}\n"
            f"iteration: {iteration}\n"
            f"current_url: {observation.get('current_url', '?')}\n"
            f"page_title: {observation.get('page_title', '?')}\n\n"
            f"=== PAGE TEXT (first 3000 chars) ===\n"
            f"{observation.get('page_text_snippet', '')}\n\n"
            f"=== PAGE HTML SNIPPET (first 5000 chars) ===\n"
            f"{observation.get('page_html_snippet', '')}\n\n"
            f"=== INTERACTIVE ELEMENTS ===\n{elements_summary}\n\n"
            f"=== RECENT HISTORY ===\n{history_text}\n\n"
            "Choose the next tool to call."
        )

        raw = await self._call_llm(self._system_prompt, user_prompt)
        return self._parse_json(raw)

    async def call_with_prompt(self, system: str, user: str) -> dict[str, Any]:
        """
        Low-level helper: send a custom system + user prompt to the LLM and
        return the parsed JSON response.

        Used by career_finder.py and job_scraper.py for domain-specific extraction.
        """
        raw = await self._call_llm(system, user)
        return self._parse_json(raw)

    # ── LLM calls ────────────────────────────────────────────────────────────

    async def _call_llm(self, system: str, user: str) -> str:
        """Route to the configured provider and return the raw text response."""
        if self._provider == "openai":
            return await self._call_openai(system, user)
        elif self._provider == "anthropic":
            return await self._call_anthropic(system, user)
        elif self._provider == "openrouter":
            return await self._call_openrouter(system, user)
        else:
            raise ValueError(f"Unknown AI_PROVIDER: {self._provider!r}")

    async def _call_openai(self, system: str, user: str) -> str:
        client = _get_openai_client()
        logger.debug("Calling OpenAI ({}) …", OPENAI_MODEL)
        response = await client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.0,
            max_tokens=2048,
        )
        text = response.choices[0].message.content or ""
        logger.debug("OpenAI response: {}", text[:200])
        return text

    async def _call_anthropic(self, system: str, user: str) -> str:
        client = _get_anthropic_client()
        logger.debug("Calling Anthropic ({}) …", ANTHROPIC_MODEL)
        response = await client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=2048,
            system=system,
            messages=[{"role": "user", "content": user}],
            temperature=0.0,
        )
        text = response.content[0].text if response.content else ""
        logger.debug("Anthropic response: {}", text[:200])
        return text

    async def _call_openrouter(self, system: str, user: str) -> str:
        client = _get_openrouter_client()
        logger.debug("Calling OpenRouter ({}) …", OPENROUTER_MODEL)
        response = await client.chat.completions.create(
            model=OPENROUTER_MODEL,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.0,
            max_tokens=2048,
        )
        text = response.choices[0].message.content or ""
        logger.debug("OpenRouter response: {}", text[:200])
        return text

    # ── Utilities ─────────────────────────────────────────────────────────────

    @staticmethod
    def _parse_json(raw: str) -> dict[str, Any]:
        """
        Extract and parse JSON from the LLM response, tolerating markdown fences.
        """
        cleaned = re.sub(r"```(?:json)?\s*", "", raw).strip().rstrip("`").strip()
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            match = re.search(r"(\{.*\}|\[.*\])", cleaned, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(1))
                except json.JSONDecodeError:
                    pass
            logger.warning("Could not parse JSON from LLM response: {}", raw[:300])
            return {}
