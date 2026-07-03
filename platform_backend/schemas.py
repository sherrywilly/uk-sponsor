from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class CompanyCreate(BaseModel):
    name: str = Field(min_length=1)
    homepage_url: str


class CompanyOut(BaseModel):
    id: int
    name: str
    domain: str
    homepage_url: str
    careers_url: str | None
    ats_provider: str | None

    class Config:
        from_attributes = True


class JobOut(BaseModel):
    id: int
    company_id: int
    source_url: str
    apply_url: str | None
    title: str
    location: str | None
    department: str | None
    employment_type: str | None
    salary: str | None
    visa_sponsorship: str | None
    ats_provider: str | None
    created_at: datetime

    class Config:
        from_attributes = True


class ActionOut(BaseModel):
    id: int
    company_id: int | None
    run_id: int | None
    action_type: str
    details: str
    created_at: datetime

    class Config:
        from_attributes = True


class QueueSubmitResponse(BaseModel):
    queued: bool
    message: str


class SettingsUpdate(BaseModel):
    queue_concurrency: int = Field(ge=1, le=10)


class SettingsOut(BaseModel):
    queue_concurrency: int


class AnalyticsOut(BaseModel):
    companies: int
    jobs: int
    runs_in_progress: int
    runs_completed: int
