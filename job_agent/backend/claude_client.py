from __future__ import annotations

import json
from typing import Any

from anthropic import AsyncAnthropic

from .config import SETTINGS
from .database import Database


class ClaudeClient:
    def __init__(self, db: Database) -> None:
        self.db = db
        self._client = AsyncAnthropic(api_key=SETTINGS.anthropic_api_key) if SETTINGS.anthropic_api_key else None

    async def extract_form_actions(self, fields_json: dict, profile_json: dict, job_id: int | None = None) -> list[dict]:
        system_prompt = (
            "You are a browser form-filling planner. Return compact JSON array only, with keys s, st, a, v."
        )
        user_prompt = json.dumps({"fields": fields_json, "profile": profile_json})
        default = self._fallback_actions(fields_json)
        return await self._json_call(
            operation="form_actions",
            model=SETTINGS.default_model_haiku,
            system_prompt=system_prompt,
            dynamic_prompt=user_prompt,
            fallback=default,
            job_id=job_id,
            max_tokens=500,
        )

    async def extract_form_actions_vision(
        self,
        screenshot_b64: str,
        profile_json: dict,
        job_id: int | None = None,
    ) -> list[dict]:
        system_prompt = (
            "You are a browser form-filling planner from screenshot context. Output compact JSON only with keys s, st, a, v."
        )
        user_prompt = json.dumps({"screenshot": screenshot_b64[:128], "profile": profile_json})
        return await self._json_call(
            operation="form_actions_vision",
            model=SETTINGS.default_model_haiku,
            system_prompt=system_prompt,
            dynamic_prompt=user_prompt,
            fallback=[],
            job_id=job_id,
            max_tokens=500,
        )

    async def generate_cover_letter(
        self,
        company: str,
        role: str,
        jd_keywords: list[str],
        profile_summary: str,
        job_id: int | None = None,
    ) -> str:
        system_prompt = "Write a concise job cover letter under 200 words."
        user_prompt = json.dumps(
            {
                "company": company,
                "role": role,
                "keywords": jd_keywords[:5],
                "profile": profile_summary,
            }
        )
        response = await self._text_call(
            operation="cover_letter",
            model=SETTINGS.default_model_haiku,
            system_prompt=system_prompt,
            dynamic_prompt=user_prompt,
            fallback="Please consider my application. I bring strong, practical engineering experience.",
            job_id=job_id,
            max_tokens=280,
        )
        return response.strip()

    async def tailor_cv_gap(
        self,
        base_cv_json: dict[str, Any],
        compressed_jd: dict[str, Any],
        job_id: int | None = None,
    ) -> dict[str, Any]:
        system_prompt = (
            "Return CV diff JSON only. Do not return full CV. Never invent new experience."
        )
        user_prompt = json.dumps({"base_cv": base_cv_json, "jd": compressed_jd})
        fallback = {
            "match_score": 75,
            "summary_rewrite": "",
            "skills_add": [],
            "skills_remove": [],
            "experience_edits": [],
            "keywords_to_inject": compressed_jd.get("tech_stack", [])[:5],
        }
        return await self._json_call(
            operation="cv_gap_analysis",
            model=SETTINGS.default_model_sonnet,
            system_prompt=system_prompt,
            dynamic_prompt=user_prompt,
            fallback=fallback,
            job_id=job_id,
            max_tokens=900,
        )

    async def _json_call(
        self,
        *,
        operation: str,
        model: str,
        system_prompt: str,
        dynamic_prompt: str,
        fallback: Any,
        job_id: int | None,
        max_tokens: int,
    ) -> Any:
        text = await self._text_call(
            operation=operation,
            model=model,
            system_prompt=system_prompt,
            dynamic_prompt=dynamic_prompt,
            fallback=json.dumps(fallback),
            job_id=job_id,
            max_tokens=max_tokens,
        )
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return fallback

    async def _text_call(
        self,
        *,
        operation: str,
        model: str,
        system_prompt: str,
        dynamic_prompt: str,
        fallback: str,
        job_id: int | None,
        max_tokens: int,
    ) -> str:
        if not self._client:
            await self.db.insert_token_log(
                job_id=job_id,
                operation=operation,
                model=model,
                input_tokens=0,
                output_tokens=0,
                cached_tokens=0,
                cost_usd=0,
            )
            return fallback

        response = await self._client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=[
                {
                    "type": "text",
                    "text": system_prompt,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[
                {
                    "role": "user",
                    "content": [{"type": "text", "text": dynamic_prompt}],
                }
            ],
        )

        output_text = "".join(block.text for block in response.content if getattr(block, "text", None))
        usage = response.usage
        input_tokens = int(getattr(usage, "input_tokens", 0) or 0)
        output_tokens = int(getattr(usage, "output_tokens", 0) or 0)
        cached_tokens = int(getattr(usage, "cache_read_input_tokens", 0) or 0)

        # Coarse estimated cost in USD. Adjust with exact vendor pricing if needed.
        estimated_cost = (input_tokens + output_tokens + (cached_tokens * 0.1)) / 1_000_000 * 3.0

        await self.db.insert_token_log(
            job_id=job_id,
            operation=operation,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cached_tokens=cached_tokens,
            cost_usd=estimated_cost,
        )

        return output_text or fallback

    def _fallback_actions(self, fields_json: dict) -> list[dict]:
        actions = []
        for field in fields_json.get("f", [])[:10]:
            name = field.get("n", "")
            value_key = "email" if "mail" in name.lower() else "name.first"
            actions.append({"s": name, "st": "get_by_label", "a": "fill", "v": value_key})
        actions.append({"s": "Submit", "st": "get_by_role", "a": "click", "v": None})
        return actions
