from __future__ import annotations

import base64
import hashlib
import os
from dataclasses import dataclass


@dataclass(slots=True)
class Settings:
    database_url: str = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./output/recruitment.db")
    queue_concurrency: int = int(os.getenv("QUEUE_CONCURRENCY", "2"))
    max_jobs_per_company: int = int(os.getenv("MAX_JOBS_PER_COMPANY", "25"))
    cache_ttl_seconds: int = int(os.getenv("CACHE_TTL_SECONDS", str(60 * 60 * 24)))
    app_queue_concurrency: int = int(os.getenv("APP_QUEUE_CONCURRENCY", "2"))
    auto_apply_enabled: bool = os.getenv("AUTO_APPLY_ENABLED", "false").lower() == "true"
    match_threshold: float = float(os.getenv("MATCH_THRESHOLD", "0.65"))
    auth_secret_key: str = os.getenv("AUTH_SECRET_KEY", "change-me-phase4-secret")
    auth_algorithm: str = os.getenv("AUTH_ALGORITHM", "HS256")
    auth_token_expiry_minutes: int = int(os.getenv("AUTH_TOKEN_EXPIRY_MINUTES", "120"))
    browser_headless: bool = False
    notification_email_webhook: str = os.getenv("NOTIFICATION_EMAIL_WEBHOOK", "")
    notification_slack_webhook: str = os.getenv("NOTIFICATION_SLACK_WEBHOOK", "")
    notification_discord_webhook: str = os.getenv("NOTIFICATION_DISCORD_WEBHOOK", "")
    notification_telegram_webhook: str = os.getenv("NOTIFICATION_TELEGRAM_WEBHOOK", "")
    data_encryption_key: str = os.getenv("DATA_ENCRYPTION_KEY", "")

    def resolved_encryption_key(self) -> str:
        if self.data_encryption_key:
            return self.data_encryption_key
        digest = hashlib.sha256(self.auth_secret_key.encode("utf-8")).digest()
        return base64.urlsafe_b64encode(digest).decode("utf-8")


settings = Settings()
