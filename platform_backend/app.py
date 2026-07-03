from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from platform_backend.api.routes import router
from platform_backend.config import settings
from platform_backend.database import AsyncSessionLocal, Base, engine
from platform_backend.services.crawl_orchestrator import CrawlOrchestrator
from platform_backend.services.event_hub import EventHub
from platform_backend.services.queue_manager import CrawlQueueManager


def create_app() -> FastAPI:
    app = FastAPI(title="AI Recruitment Platform", version="3.0.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(router)

    @app.on_event("startup")
    async def on_startup() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        event_hub = EventHub()
        orchestrator = CrawlOrchestrator(
            session_factory=AsyncSessionLocal,
            event_hub=event_hub,
            max_jobs_per_company=settings.max_jobs_per_company,
        )
        queue = CrawlQueueManager(orchestrator, concurrency=settings.queue_concurrency)
        await queue.start()

        app.state.event_hub = event_hub
        app.state.queue_manager = queue

    @app.on_event("shutdown")
    async def on_shutdown() -> None:
        queue = getattr(app.state, "queue_manager", None)
        if queue is not None:
            await queue.stop()

    return app


app = create_app()
