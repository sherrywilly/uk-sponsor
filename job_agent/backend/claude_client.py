from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from typing import Any

from .database import Database

try:
    from anthropic import AsyncAnthropic
except ImportError:  # pragma: no cover
    AsyncAnthropic = None


@dataclass(slots=True)
class Usage:
    input_tokens: int
    output_tokens: int
    cache_read_input_tokens: int = 0


class ClaudeClient:
    def __init__(self, *, api_key: str, model_haiku: str, model_sonnet: str, db: Database) -> None:
        self.model_haiku = model_haiku
        self.model_sonnet = model_sonnet
        self.db = db
        self.client = AsyncAnthropic(api_key=api_key) if (api_key and AsyncAnthropic) else None

    async def extract_form_actions(self, fields_json: dict[str, Any], profile_json: dict[str, Any], job_id: int | None = None) -> list[dict[str, Any]]:
        system = {
            "type": "text",
            "text": "Return compact JSON actions with keys s,st,a,v only.",
            "cache_control": {"type": "ephemeral"},
        }
        user_text = json.dumps({"fields": fields_json, "profile": profile_json}, separators=(",", ":"))
        if not self.client:
            actions = self._fallback_actions(fields_json)
            await self._log(job_id, "form_fill", self.model_haiku, Usage(input_tokens=len(user_text) // 4, output_tokens=40, cache_read_input_tokens=120), 0.00004)
            return actions

        msg = await self.client.messages.create(
            model=self.model_haiku,
            max_tokens=450,
            system=[system],
            messages=[{"role": "user", "content": [{"type": "text", "text": user_text}]}],
        )
        payload = self._read_text(msg)
        data = json.loads(payload)
        actions = [self._expand_action(a) for a in data]
        usage = Usage(
            input_tokens=getattr(msg.usage, "input_tokens", 0),
            output_tokens=getattr(msg.usage, "output_tokens", 0),
            cache_read_input_tokens=getattr(msg.usage, "cache_read_input_tokens", 0),
        )
        await self._log(job_id, "form_fill", self.model_haiku, usage, self._estimate_cost(usage, "haiku"))
        return actions

    async def extract_form_actions_vision(self, screenshot_b64: bytes, profile_json: dict[str, Any], job_id: int | None = None) -> list[dict[str, Any]]:
        resized_b64 = base64.b64encode(screenshot_b64).decode("utf-8")
        system = {
            "type": "text",
            "text": "Identify form actions from screenshot; compact JSON list with s,st,a,v.",
            "cache_control": {"type": "ephemeral"},
        }

        if not self.client:
            await self._log(job_id, "vision_form_fill", self.model_haiku, Usage(input_tokens=500, output_tokens=80, cache_read_input_tokens=180), 0.001)
            return []

        msg = await self.client.messages.create(
            model=self.model_haiku,
            max_tokens=500,
            system=[system],
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": json.dumps({"profile": profile_json})},
                        {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": resized_b64}},
                    ],
                }
            ],
        )
        payload = self._read_text(msg)
        data = json.loads(payload)
        actions = [self._expand_action(a) for a in data]
        usage = Usage(
            input_tokens=getattr(msg.usage, "input_tokens", 0),
            output_tokens=getattr(msg.usage, "output_tokens", 0),
            cache_read_input_tokens=getattr(msg.usage, "cache_read_input_tokens", 0),
        )
        await self._log(job_id, "vision_form_fill", self.model_haiku, usage, self._estimate_cost(usage, "haiku"))
        return actions

    async def generate_cover_letter(
        self,
        company: str,
        role: str,
        jd_keywords: list[str],
        profile_summary: str,
        job_id: int | None = None,
    ) -> str:
        system = {
            "type": "text",
            "text": "Write a concise <200 words cover letter.",
            "cache_control": {"type": "ephemeral"},
        }
        prompt = json.dumps(
            {
                "company": company,
                "role": role,
                "keywords": jd_keywords[:5],
                "profile": profile_summary,
            }
        )
        if not self.client:
            await self._log(job_id, "cover_letter", self.model_haiku, Usage(input_tokens=200, output_tokens=120, cache_read_input_tokens=120), 0.00003)
            return f"Dear {company} hiring team, I am excited to apply for the {role} role..."

        msg = await self.client.messages.create(
            model=self.model_haiku,
            max_tokens=260,
            system=[system],
            messages=[{"role": "user", "content": [{"type": "text", "text": prompt}]}],
        )
        text = self._read_text(msg)
        usage = Usage(
            input_tokens=getattr(msg.usage, "input_tokens", 0),
            output_tokens=getattr(msg.usage, "output_tokens", 0),
            cache_read_input_tokens=getattr(msg.usage, "cache_read_input_tokens", 0),
        )
        await self._log(job_id, "cover_letter", self.model_haiku, usage, self._estimate_cost(usage, "haiku"))
        return text

    async def tailor_cv_gap(self, base_cv_json: dict[str, Any], compressed_jd: dict[str, Any], job_id: int | None = None) -> dict[str, Any]:
        system = {
            "type": "text",
            "text": "Return CV diff JSON only; do not rewrite full CV.",
            "cache_control": {"type": "ephemeral"},
        }
        prompt = json.dumps({"base_cv": base_cv_json, "jd": compressed_jd}, separators=(",", ":"))

        if not self.client:
            diff = {
                "match_score": 75,
                "summary_rewrite": "Experienced engineer focused on backend and automation.",
                "skills_add": compressed_jd.get("tech_stack", [])[:3],
                "skills_remove": [],
                "experience_edits": [],
                "keywords_to_inject": compressed_jd.get("tech_stack", [])[:6],
            }
            await self._log(job_id, "cv_gap", self.model_sonnet, Usage(input_tokens=400, output_tokens=250, cache_read_input_tokens=350), 0.0002)
            return diff

        msg = await self.client.messages.create(
            model=self.model_sonnet,
            max_tokens=900,
            system=[system],
            messages=[{"role": "user", "content": [{"type": "text", "text": prompt}]}],
        )
        payload = self._read_text(msg)
        diff = json.loads(payload)
        usage = Usage(
            input_tokens=getattr(msg.usage, "input_tokens", 0),
            output_tokens=getattr(msg.usage, "output_tokens", 0),
            cache_read_input_tokens=getattr(msg.usage, "cache_read_input_tokens", 0),
        )
        await self._log(job_id, "cv_gap", self.model_sonnet, usage, self._estimate_cost(usage, "sonnet"))
        return diff

    async def _log(self, job_id: int | None, operation: str, model: str, usage: Usage, cost_usd: float) -> None:
        await self.db.insert_token_log(
            job_id=job_id,
            operation=operation,
            model=model,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            cached_tokens=usage.cache_read_input_tokens,
            cost_usd=cost_usd,
        )

    def _estimate_cost(self, usage: Usage, tier: str) -> float:
        # Rough estimator; cached input is priced at 10% of input token pricing.
        if tier == "sonnet":
            in_rate = 0.000003
            out_rate = 0.000015
        else:
            in_rate = 0.0000008
            out_rate = 0.000004
        billable_in = max(usage.input_tokens - usage.cache_read_input_tokens, 0)
        cached_in = usage.cache_read_input_tokens
        return round((billable_in * in_rate) + (cached_in * in_rate * 0.1) + (usage.output_tokens * out_rate), 6)

    @staticmethod
    def _read_text(msg: Any) -> str:
        chunks = getattr(msg, "content", [])
        parts = [c.text for c in chunks if getattr(c, "type", None) == "text"]
        return "\n".join(parts).strip()

    @staticmethod
    def _expand_action(item: dict[str, Any]) -> dict[str, Any]:
        return {
            "selector": item.get("s", ""),
            "strategy": item.get("st", "css"),
            "action": item.get("a", "fill"),
            "value": item.get("v", ""),
        }

    @staticmethod
    def _fallback_actions(fields_json: dict[str, Any]) -> list[dict[str, Any]]:
        actions: list[dict[str, Any]] = []
        for f in fields_json.get("f", [])[:20]:
            typ = (f.get("t") or "text").lower()
            if typ in {"button", "submit"}:
                actions.append({"selector": f.get("k") or "Submit", "strategy": "get_by_role", "action": "click", "value": ""})
            elif typ == "file":
                actions.append({"selector": f.get("k") or "Resume", "strategy": "get_by_label", "action": "upload", "value": "cv_path"})
            elif typ == "select":
                actions.append({"selector": f.get("s") or f.get("k"), "strategy": "css", "action": "select", "value": "location"})
            else:
                actions.append({"selector": f.get("k") or f.get("s"), "strategy": "get_by_label", "action": "fill", "value": "email"})
        return actions
