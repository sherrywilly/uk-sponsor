from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv()

ROOT_DIR = Path(__file__).resolve().parents[1]
RECORDING_DIR = ROOT_DIR / "recordings"
SCREENSHOT_DIR = ROOT_DIR / "screenshots"
CV_OUTPUT_DIR = ROOT_DIR / "cvs"
COVER_LETTER_DIR = ROOT_DIR / "cover_letters"
LOG_DIR = ROOT_DIR / "logs"

for folder in (RECORDING_DIR, SCREENSHOT_DIR, CV_OUTPUT_DIR, COVER_LETTER_DIR, LOG_DIR):
    folder.mkdir(parents=True, exist_ok=True)


@dataclass(slots=True)
class Settings:
    db_path: Path
    anthropic_api_key: str
    model_haiku: str
    model_sonnet: str
    profile: dict[str, Any]
    base_cv_path: Path
    base_cv_text: str


def _load_profile() -> dict[str, Any]:
    profile_json = os.getenv("PROFILE_JSON", "")
    if profile_json:
        try:
            return json.loads(profile_json)
        except json.JSONDecodeError:
            pass
    return {
        "name": {"first": "", "last": ""},
        "email": "",
        "phone": "",
        "location": "",
        "linkedin": "",
        "github": "",
        "work_auth": "",
    }


def _read_cv_text(path: Path) -> str:
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return ""


def load_settings() -> Settings:
    base_cv_path = ROOT_DIR / os.getenv("BASE_CV_PATH", "base_cv.docx")
    return Settings(
        db_path=ROOT_DIR / os.getenv("SQLITE_PATH", "job_agent.db"),
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", ""),
        model_haiku=os.getenv("MODEL_HAIKU", "claude-3-5-haiku-latest"),
        model_sonnet=os.getenv("MODEL_SONNET", "claude-3-5-sonnet-latest"),
        profile=_load_profile(),
        base_cv_path=base_cv_path,
        base_cv_text=_read_cv_text(base_cv_path),
    )


SETTINGS = load_settings()
