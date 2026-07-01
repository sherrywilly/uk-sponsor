"""
agent.py — LLM-powered reasoning layer.

Supports both OpenAI and Anthropic as providers, selected via the AI_PROVIDER
environment variable.  The agent is called with a structured prompt describing
the current page state and returns structured JSON decisions that the rest of
the application can act upon.
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

AI_PROVIDER: str = os.getenv("AI_PROVIDER", "openai").lower()
OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o")
ANTHROPIC_MODEL: str = os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-20241022")


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


# ── System prompts ────────────────────────────────────────────────────────────

_NAVIGATION_SYSTEM = """
You are an expert web-navigation AI agent. You inspect the current state of a
webpage and decide the single next action to take in order to find the company's
Careers / Jobs page.

You understand that careers pages may be labelled:
  Careers, Jobs, Join Us, Work With Us, Opportunities, Hiring, Vacancies,
  Open Positions, We're Hiring, Team, People, Culture, etc.

Respond ONLY with valid JSON matching this schema (no markdown fences):
{
  "action": "click_link" | "click_button" | "navigate" | "scroll" | "found" | "give_up",
  "target": "<link text, button text, or full URL>",
  "reason": "<one-sentence explanation>"
}

Rules:
- Use "found" when you are already on (or have found the URL of) the careers page.
- Use "navigate" only when you have a direct URL to go to (set target=URL).
- Use "give_up" after 10+ failed attempts or when there is clearly no careers page.
- Never use "give_up" before thoroughly exploring the navigation.
"""

_EXTRACTION_SYSTEM = """
You are an expert job-data extraction AI. Given the HTML / text of a job posting
page, extract structured information and return ONLY valid JSON (no markdown).

Return exactly this structure (use null for missing fields):
{
  "job_title": "...",
  "location": "...",
  "department": "...",
  "employment_type": "...",
  "salary": "...",
  "job_description": "...",
  "required_skills": ["..."],
  "preferred_skills": ["..."],
  "visa_sponsorship": "...",
  "apply_url": "..."
}

For visa_sponsorship, look for:
- Explicit mention of visa sponsorship, right-to-work requirements, or work
  authorisation statements.
- If nothing is mentioned, return null.
- Summarise concisely (e.g. "Visa sponsorship available", "No sponsorship offered",
  "Applicants must have the right to work in the UK").
"""

_JOB_LIST_SYSTEM = """
You are an expert web-analysis AI. Given the HTML / text of a careers listing
page, identify all job postings and return ONLY valid JSON (no markdown):

{
  "job_links": [
    {"title": "...", "url": "..."},
    ...
  ]
}

Include every individual job posting URL you find. Do not include category pages,
pagination links, or filter controls — only actual job listings.
If no individual jobs are found (e.g. it's still a category landing page), return
{"job_links": []}.
"""


# ── Core agent class ──────────────────────────────────────────────────────────


class AIAgent:
    """Thin async wrapper around the chosen LLM provider."""

    def __init__(self) -> None:
        self._provider = AI_PROVIDER
        logger.info("AI agent initialised with provider: {}", self._provider)

    # ── Public methods ────────────────────────────────────────────────────────

    async def decide_navigation_action(
        self,
        page_text: str,
        interactive_elements: list[dict],
        current_url: str,
        attempt: int,
    ) -> dict[str, Any]:
        """
        Given the current page state, decide the next navigation action.
        Returns a parsed dict with keys: action, target, reason.
        """
        elements_summary = "\n".join(
            f"  [{i}] {el['tag'].upper()} | text='{el['text']}' | href='{el.get('href', '')}'"
            for i, el in enumerate(interactive_elements[:80])  # cap at 80 items
        )

        user_prompt = (
            f"Current URL: {current_url}\n"
            f"Attempt: {attempt}\n\n"
            f"=== PAGE TEXT (first 3000 chars) ===\n{page_text[:3000]}\n\n"
            f"=== INTERACTIVE ELEMENTS ===\n{elements_summary}\n\n"
            "Decide the next action to find the Careers/Jobs page."
        )

        raw = await self._call_llm(_NAVIGATION_SYSTEM, user_prompt)
        return self._parse_json(raw)

    async def extract_job_links(self, page_text: str, page_html: str, current_url: str) -> list[dict]:
        """
        From a careers listing page, extract all individual job URLs.
        Returns a list of {title, url} dicts.
        """
        user_prompt = (
            f"Current URL: {current_url}\n\n"
            f"=== PAGE TEXT (first 4000 chars) ===\n{page_text[:4000]}\n\n"
            f"=== PAGE HTML SNIPPET (first 6000 chars) ===\n{page_html[:6000]}\n\n"
            "Return all individual job listing URLs you can find."
        )
        raw = await self._call_llm(_JOB_LIST_SYSTEM, user_prompt)
        data = self._parse_json(raw)
        return data.get("job_links", [])

    async def extract_job_details(
        self, page_text: str, page_html: str, current_url: str, company: str
    ) -> dict[str, Any]:
        """
        From an individual job posting page, extract structured job data.
        Returns a dict matching the extraction schema.
        """
        user_prompt = (
            f"Company: {company}\n"
            f"Job URL: {current_url}\n\n"
            f"=== PAGE TEXT (first 5000 chars) ===\n{page_text[:5000]}\n\n"
            f"=== PAGE HTML SNIPPET (first 8000 chars) ===\n{page_html[:8000]}\n\n"
            "Extract all job details."
        )
        raw = await self._call_llm(_EXTRACTION_SYSTEM, user_prompt)
        return self._parse_json(raw)

    # ── LLM calls ────────────────────────────────────────────────────────────

    async def _call_llm(self, system: str, user: str) -> str:
        """Route to the configured provider and return the raw text response."""
        if self._provider == "openai":
            return await self._call_openai(system, user)
        elif self._provider == "anthropic":
            return await self._call_anthropic(system, user)
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

    # ── Utilities ─────────────────────────────────────────────────────────────

    @staticmethod
    def _parse_json(raw: str) -> dict[str, Any]:
        """
        Extract and parse JSON from the LLM response, tolerating markdown fences.
        """
        # Strip markdown code fences if present
        cleaned = re.sub(r"```(?:json)?\s*", "", raw).strip().rstrip("`").strip()
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            # Try to find a JSON object / array anywhere in the response
            match = re.search(r"(\{.*\}|\[.*\])", cleaned, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(1))
                except json.JSONDecodeError:
                    pass
            logger.warning("Could not parse JSON from LLM response: {}", raw[:300])
            return {}
