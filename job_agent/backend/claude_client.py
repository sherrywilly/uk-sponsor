from __future__ import annotations

import json
from typing import Any

from anthropic import Anthropic

from .config import BASE_CV_TEXT, PROFILE, SETTINGS
from .database import Database


class ClaudeClient:
    def __init__(self, db: Database, job_id: int | None = None) -> None:
        if not SETTINGS.anthropic_api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is required to run Claude operations")
        self.client = Anthropic(api_key=SETTINGS.anthropic_api_key, base_url=SETTINGS.anthropic_base_url)
        self.db = db
        self.job_id = job_id

    async def _log_usage(self, operation: str, model: str, usage: Any) -> None:
        input_tokens = int(getattr(usage, "input_tokens", 0) or 0)
        output_tokens = int(getattr(usage, "output_tokens", 0) or 0)
        cache_read = int(getattr(usage, "cache_read_input_tokens", 0) or 0)
        cache_creation = int(getattr(usage, "cache_creation_input_tokens", 0) or 0)
        cached_tokens = cache_read + cache_creation
        cost_usd = ((input_tokens - cache_read) * 0.0000008) + (cache_read * 0.00000008) + (output_tokens * 0.000004)
        await self.db.insert_token_log(
            job_id=self.job_id,
            operation=operation,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cached_tokens=cached_tokens,
            cost_usd=cost_usd,
        )

    def _cached_block(self, text: str) -> dict[str, Any]:
        return {
            "type": "text",
            "text": text,
            "cache_control": {"type": "ephemeral"},
        }

    async def extract_form_actions(self, fields_json: dict[str, Any], profile_json: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        profile_json = profile_json or PROFILE
        prompt = (
            "Return compact action steps for filling this job form. "
            "Use keys s(selector), st(strategy), a(action), v(profile_key). "
            "Allowed actions: fill, select, upload, click."
        )
        resp = self.client.messages.create(
            model=SETTINGS.model_haiku,
            max_tokens=700,
            system=[self._cached_block("You are a precise form automation planner.")],
            messages=[
                {"role": "user", "content": [self._cached_block(json.dumps(profile_json)), {"type": "text", "text": json.dumps(fields_json)}, {"type": "text", "text": prompt}]}
            ],
        )
        await self._log_usage("form_actions", SETTINGS.model_haiku, resp.usage)
        text = "".join(block.text for block in resp.content if getattr(block, "type", "") == "text")
        actions = json.loads(text)
        return [self.expand_action(a) for a in actions]

    async def extract_form_actions_vision(self, screenshot_b64: str, profile_json: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        profile_json = profile_json or PROFILE
        resp = self.client.messages.create(
            model=SETTINGS.model_haiku,
            max_tokens=700,
            system=[self._cached_block("You convert screenshot forms into actionable JSON steps.")],
            messages=[
                {
                    "role": "user",
                    "content": [
                        self._cached_block(json.dumps(profile_json)),
                        {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": screenshot_b64}},
                        {"type": "text", "text": "Return compact JSON actions with keys s/st/a/v only."},
                    ],
                }
            ],
        )
        await self._log_usage("form_actions_vision", SETTINGS.model_haiku, resp.usage)
        text = "".join(block.text for block in resp.content if getattr(block, "type", "") == "text")
        actions = json.loads(text)
        return [self.expand_action(a) for a in actions]

    async def generate_cover_letter(self, company: str, role: str, jd_keywords: list[str], profile_summary: str) -> str:
        resp = self.client.messages.create(
            model=SETTINGS.model_haiku,
            max_tokens=400,
            system=[self._cached_block("Write concise professional cover letters under 200 words.")],
            messages=[
                {
                    "role": "user",
                    "content": [
                        self._cached_block(profile_summary),
                        {"type": "text", "text": json.dumps({"company": company, "role": role, "keywords": jd_keywords[:5]})},
                    ],
                }
            ],
        )
        await self._log_usage("cover_letter", SETTINGS.model_haiku, resp.usage)
        return "".join(block.text for block in resp.content if getattr(block, "type", "") == "text")

    async def tailor_cv_gap(self, compressed_jd: dict[str, Any]) -> dict[str, Any]:
        base_cv_json = {"base_cv": BASE_CV_TEXT}
        resp = self.client.messages.create(
            model=SETTINGS.model_sonnet,
            max_tokens=900,
            system=[self._cached_block("Return JSON diff updates only. Never fabricate experience.")],
            messages=[
                {
                    "role": "user",
                    "content": [
                        self._cached_block(json.dumps(base_cv_json)),
                        {"type": "text", "text": json.dumps(compressed_jd)},
                    ],
                }
            ],
        )
        await self._log_usage("cv_tailor", SETTINGS.model_sonnet, resp.usage)
        text = "".join(block.text for block in resp.content if getattr(block, "type", "") == "text")
        return json.loads(text)

    @staticmethod
    def expand_action(action: dict[str, Any]) -> dict[str, Any]:
        return {
            "selector": action.get("s", ""),
            "strategy": action.get("st", "css"),
            "action": action.get("a", "fill"),
            "value": action.get("v", ""),
        }
