from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RECORDING_DIR = PROJECT_ROOT / "recordings"
SCREENSHOT_DIR = PROJECT_ROOT / "screenshots"
CV_OUTPUT_DIR = PROJECT_ROOT / "cvs"
COVER_LETTER_DIR = PROJECT_ROOT / "cover_letters"
LOG_DIR = PROJECT_ROOT / "logs"
DB_PATH = PROJECT_ROOT / "agent.db"

for _path in [RECORDING_DIR, SCREENSHOT_DIR, CV_OUTPUT_DIR, COVER_LETTER_DIR, LOG_DIR]:
    _path.mkdir(parents=True, exist_ok=True)

BASE_CV_PATH = Path(os.getenv("BASE_CV_PATH", str(PROJECT_ROOT / "base_cv.docx")))
BASE_CV_TEXT_PATH = Path(os.getenv("BASE_CV_TEXT_PATH", str(PROJECT_ROOT / "base_cv.txt")))


def _load_base_cv_text() -> str:
    if BASE_CV_TEXT_PATH.exists():
        return BASE_CV_TEXT_PATH.read_text(encoding="utf-8", errors="ignore")
    return ""


def _load_profile() -> dict[str, Any]:
    raw_profile = os.getenv("CANDIDATE_PROFILE_JSON", "")
    if raw_profile:
        try:
            return json.loads(raw_profile)
        except json.JSONDecodeError:
            pass
    return {
        "name": {
            "first": os.getenv("PROFILE_FIRST_NAME", ""),
            "last": os.getenv("PROFILE_LAST_NAME", ""),
        },
        "email": os.getenv("PROFILE_EMAIL", ""),
        "phone": os.getenv("PROFILE_PHONE", ""),
        "location": os.getenv("PROFILE_LOCATION", ""),
        "linkedin": os.getenv("PROFILE_LINKEDIN", ""),
        "github": os.getenv("PROFILE_GITHUB", ""),
        "visa_status": os.getenv("PROFILE_VISA_STATUS", ""),
        "summary": os.getenv("PROFILE_SUMMARY", ""),
        "cv_path": str(BASE_CV_PATH),
    }


PROFILE = _load_profile()
BASE_CV_TEXT = _load_base_cv_text()


@dataclass(slots=True)
class Settings:
    anthropic_api_key: str
    anthropic_base_url: str | None
    model_haiku: str
    model_sonnet: str
    playwright_headless: bool
    concurrency: int


SETTINGS = Settings(
    anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", ""),
    anthropic_base_url=os.getenv("ANTHROPIC_BASE_URL") or None,
    model_haiku=os.getenv("MODEL_HAIKU", "claude-haiku-4-5"),
    model_sonnet=os.getenv("MODEL_SONNET", "claude-sonnet-4-6"),
    playwright_headless=os.getenv("PLAYWRIGHT_HEADLESS", "true").lower() == "true",
    concurrency=max(1, min(5, int(os.getenv("AGENT_CONCURRENCY", "1")))),
)
