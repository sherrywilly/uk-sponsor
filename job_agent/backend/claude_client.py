from __future__ import annotations

import json
from typing import Any

import httpx

from .config import BASE_CV_TEXT, PROFILE, SETTINGS
from .database import Database


class ClaudeClient:
    def __init__(self, db: Database, job_id: int | None = None) -> None:
        if not SETTINGS.openrouter_api_key:
            raise RuntimeError("OPENROUTER_API_KEY is required to run model operations")
        self.db = db
        self.job_id = job_id

    async def _log_usage(self, operation: str, model: str, usage: dict[str, Any]) -> None:
        input_tokens = int(usage.get("prompt_tokens", 0) or 0)
        output_tokens = int(usage.get("completion_tokens", 0) or 0)
        cached_tokens = int(usage.get("cached_tokens", 0) or 0)
        cost_usd = 0.0
        await self.db.insert_token_log(
            job_id=self.job_id,
            operation=operation,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cached_tokens=cached_tokens,
            cost_usd=cost_usd,
        )

    def _headers(self) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {SETTINGS.openrouter_api_key}",
            "Content-Type": "application/json",
        }
        if SETTINGS.openrouter_site_url:
            headers["HTTP-Referer"] = SETTINGS.openrouter_site_url
        if SETTINGS.openrouter_app_name:
            headers["X-Title"] = SETTINGS.openrouter_app_name
        return headers

    def _chat_completion(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        max_tokens: int,
        response_format: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": 0.2,
        }
        if response_format:
            payload["response_format"] = response_format

        with httpx.Client(timeout=90.0) as client:
            response = client.post(
                f"{SETTINGS.openrouter_base_url.rstrip('/')}/chat/completions",
                headers=self._headers(),
                json=payload,
            )
            response.raise_for_status()
            return response.json()

    @staticmethod
    def _extract_text(response_json: dict[str, Any]) -> str:
        choices = response_json.get("choices") or []
        if not choices:
            raise ValueError("No choices returned by OpenRouter")
        message = choices[0].get("message") or {}
        content = message.get("content", "")
        if isinstance(content, list):
            parts: list[str] = []
            for part in content:
                if isinstance(part, dict) and part.get("type") == "text":
                    parts.append(str(part.get("text", "")))
            return "".join(parts).strip()
        return str(content).strip()

    @staticmethod
    def _extract_json(text: str) -> Any:
        cleaned = text.strip()
        if cleaned.startswith("```"):
            lines = cleaned.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            cleaned = "\n".join(lines).strip()
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            start = cleaned.find("{")
            end = cleaned.rfind("}")
            if start != -1 and end != -1 and end > start:
                return json.loads(cleaned[start : end + 1])
            start = cleaned.find("[")
            end = cleaned.rfind("]")
            if start != -1 and end != -1 and end > start:
                return json.loads(cleaned[start : end + 1])
            raise

    async def extract_form_actions(self, fields_json: dict[str, Any], profile_json: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        profile_json = profile_json or PROFILE
        prompt = (
            "Return compact action steps for filling this job form as a JSON array. "
            "Use keys s(selector), st(strategy), a(action), v(profile_key). "
            "Allowed actions: fill, select, upload, click. Return only JSON."
        )
        response_json = self._chat_completion(
            model=SETTINGS.model_haiku,
            max_tokens=700,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": "You are a precise form automation planner.",
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "profile": profile_json,
                            "fields": fields_json,
                            "instruction": prompt,
                        }
                    ),
                },
            ],
        )
        await self._log_usage("form_actions", SETTINGS.model_haiku, response_json.get("usage", {}))
        text = self._extract_text(response_json)
        parsed = self._extract_json(text)
        actions = parsed.get("actions", []) if isinstance(parsed, dict) else parsed
        if not isinstance(actions, list):
            raise ValueError("Model response did not return an action list")
        return [self.expand_action(a) for a in actions if isinstance(a, dict)]

    async def extract_form_actions_vision(self, screenshot_b64: str, profile_json: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        profile_json = profile_json or PROFILE
        response_json = self._chat_completion(
            model=SETTINGS.model_haiku,
            max_tokens=700,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": "You convert screenshot forms into actionable JSON steps.",
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                "Return compact JSON actions with keys s/st/a/v only under top-level key 'actions'. "
                                f"Profile: {json.dumps(profile_json)}"
                            ),
                        },
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{screenshot_b64}"},
                        },
                    ],
                },
            ],
        )
        await self._log_usage("form_actions_vision", SETTINGS.model_haiku, response_json.get("usage", {}))
        text = self._extract_text(response_json)
        parsed = self._extract_json(text)
        actions = parsed.get("actions", []) if isinstance(parsed, dict) else parsed
        if not isinstance(actions, list):
            raise ValueError("Model vision response did not return an action list")
        return [self.expand_action(a) for a in actions if isinstance(a, dict)]

    async def generate_cover_letter(self, company: str, role: str, jd_keywords: list[str], profile_summary: str) -> str:
        response_json = self._chat_completion(
            model=SETTINGS.model_haiku,
            max_tokens=400,
            messages=[
                {
                    "role": "system",
                    "content": "Write concise professional cover letters under 200 words.",
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "profile_summary": profile_summary,
                            "company": company,
                            "role": role,
                            "keywords": jd_keywords[:5],
                        }
                    ),
                },
            ],
        )
        await self._log_usage("cover_letter", SETTINGS.model_haiku, response_json.get("usage", {}))
        return self._extract_text(response_json)

    async def tailor_cv_gap(self, compressed_jd: dict[str, Any]) -> dict[str, Any]:
        base_cv_json = {"base_cv": BASE_CV_TEXT}
        response_json = self._chat_completion(
            model=SETTINGS.model_sonnet,
            max_tokens=900,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": "Return JSON diff updates only. Never fabricate experience.",
                },
                {
                    "role": "user",
                    "content": json.dumps({"base_cv": base_cv_json, "compressed_jd": compressed_jd}),
                },
            ],
        )
        await self._log_usage("cv_tailor", SETTINGS.model_sonnet, response_json.get("usage", {}))
        text = self._extract_text(response_json)
        parsed = self._extract_json(text)
        if not isinstance(parsed, dict):
            raise ValueError("CV tailoring response must be a JSON object")
        return parsed

    @staticmethod
    def expand_action(action: dict[str, Any]) -> dict[str, Any]:
        return {
            "selector": action.get("s", ""),
            "strategy": action.get("st", "css"),
            "action": action.get("a", "fill"),
            "value": action.get("v", ""),
        }
