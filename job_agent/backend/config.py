from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

load_dotenv()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    anthropic_api_key: str | None = Field(default=None, alias="ANTHROPIC_API_KEY")
    database_path: str = Field(default="./job_agent.db", alias="DATABASE_PATH")
    base_cv_path: str = Field(default="../base_cv.docx", alias="BASE_CV_PATH")
    candidate_profile_json: str = Field(default="{}", alias="CANDIDATE_PROFILE_JSON")

    default_model_haiku: str = Field(default="claude-haiku-4-5", alias="DEFAULT_MODEL_HAIKU")
    default_model_sonnet: str = Field(default="claude-sonnet-4-6", alias="DEFAULT_MODEL_SONNET")

    app_host: str = Field(default="0.0.0.0", alias="APP_HOST")
    app_port: int = Field(default=8000, alias="APP_PORT")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    @property
    def candidate_profile(self) -> dict[str, Any]:
        try:
            return json.loads(self.candidate_profile_json)
        except json.JSONDecodeError:
            return {}


SETTINGS = Settings()

BASE_DIR = Path(__file__).resolve().parent.parent
RECORDING_DIR = BASE_DIR / "recordings"
SCREENSHOT_DIR = BASE_DIR / "screenshots"
CV_OUTPUT_DIR = BASE_DIR / "cvs"
COVER_LETTER_DIR = BASE_DIR / "cover_letters"
LOG_DIR = BASE_DIR / "logs"

for directory in [RECORDING_DIR, SCREENSHOT_DIR, CV_OUTPUT_DIR, COVER_LETTER_DIR, LOG_DIR]:
    directory.mkdir(parents=True, exist_ok=True)

BASE_CV_PATH = (BASE_DIR / SETTINGS.base_cv_path).resolve()
BASE_CV_TEXT = ""
if BASE_CV_PATH.exists():
    BASE_CV_TEXT = BASE_CV_PATH.read_bytes()[:0].decode("utf-8", errors="ignore")
