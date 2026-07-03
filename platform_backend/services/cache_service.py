from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from platform_backend.config import settings
from platform_backend.models import CrawlCache


class CacheService:
    async def get(self, session: AsyncSession, domain: str) -> CrawlCache | None:
        result = await session.execute(select(CrawlCache).where(CrawlCache.domain == domain))
        cache = result.scalar_one_or_none()
        if not cache:
            return None
        if cache.valid_until < datetime.utcnow():
            return None
        return cache

    async def upsert(
        self,
        session: AsyncSession,
        *,
        domain: str,
        careers_url: str | None,
        ats_provider: str | None,
    ) -> None:
        result = await session.execute(select(CrawlCache).where(CrawlCache.domain == domain))
        existing = result.scalar_one_or_none()
        valid_until = datetime.utcnow() + timedelta(seconds=settings.cache_ttl_seconds)
        if existing:
            existing.careers_url = careers_url
            existing.ats_provider = ats_provider
            existing.valid_until = valid_until
        else:
            session.add(
                CrawlCache(
                    domain=domain,
                    careers_url=careers_url,
                    ats_provider=ats_provider,
                    valid_until=valid_until,
                )
            )
        await session.commit()
