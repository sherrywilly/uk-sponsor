from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class JDCompressed(BaseModel):
    required_skills: list[str] = Field(default_factory=list)
    preferred_skills: list[str] = Field(default_factory=list)
    tech_stack: list[str] = Field(default_factory=list)
    seniority: str | None = None
    sponsorship_flag: str = "unknown"
    role_type: str | None = None


class JDExtractionResult(BaseModel):
    raw_text: str
    compressed: JDCompressed
    token_count: int
    sponsorship_flag: str


class ActionStep(BaseModel):
    step: int
    page_pattern: str | None = None
    action: str
    strategy: str
    selector: str
    field_type: str | None = None
    profile_key: str | None = None
    delay_before: float = 0.0


class RecordingScript(BaseModel):
    domain: str
    ats_type: str
    recorded_at: str
    success: bool
    steps: list[ActionStep]
    success_signal: str | None = None
    total_pages: int = 1


class ReplayResult(BaseModel):
    status: str
    steps_completed: int
    failed_step: int | None = None
    recording_id: int | None = None


class ExecutionResult(BaseModel):
    status: str
    success_signal: str | None = None
    screenshot_path: str | None = None
    notes: str | None = None


class CVTailorResult(BaseModel):
    cv_path: str
    pdf_path: str | None
    match_score: int
    diff: dict[str, Any]


@dataclass
class AgentEvent:
    event: str
    payload: dict[str, Any]
    at: datetime
