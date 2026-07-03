from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd
from fastapi import APIRouter, Depends, Request, WebSocket, WebSocketDisconnect
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from platform_backend.database import get_session
from platform_backend.models import ActionEvent, Company, CrawlRun, Job, SettingsKV, Workflow
from platform_backend.schemas import (
    ActionOut,
    AnalyticsOut,
    CompanyCreate,
    CompanyOut,
    JobOut,
    QueueSubmitResponse,
    SettingsOut,
    SettingsUpdate,
)

router = APIRouter()


@router.get("/health")
async def health() -> dict:
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}


@router.post("/api/companies", response_model=QueueSubmitResponse)
async def enqueue_company(payload: CompanyCreate, request: Request) -> QueueSubmitResponse:
    queue = request.app.state.queue_manager
    await queue.submit(payload.name, payload.homepage_url)
    return QueueSubmitResponse(queued=True, message="Company queued")


@router.get("/api/companies", response_model=list[CompanyOut])
async def list_companies(session: AsyncSession = Depends(get_session)) -> list[CompanyOut]:
    result = await session.execute(select(Company).order_by(Company.updated_at.desc()))
    return list(result.scalars().all())


@router.get("/api/jobs", response_model=list[JobOut])
async def list_jobs(limit: int = 200, session: AsyncSession = Depends(get_session)) -> list[JobOut]:
    result = await session.execute(select(Job).order_by(Job.created_at.desc()).limit(limit))
    return list(result.scalars().all())


@router.get("/api/activity", response_model=list[ActionOut])
async def activity(limit: int = 200, session: AsyncSession = Depends(get_session)) -> list[ActionOut]:
    result = await session.execute(select(ActionEvent).order_by(ActionEvent.created_at.desc()).limit(limit))
    return list(result.scalars().all())


@router.get("/api/analytics", response_model=AnalyticsOut)
async def analytics(session: AsyncSession = Depends(get_session)) -> AnalyticsOut:
    companies = (await session.execute(select(func.count()).select_from(Company))).scalar_one()
    jobs = (await session.execute(select(func.count()).select_from(Job))).scalar_one()
    in_progress = (
        await session.execute(
            select(func.count()).select_from(CrawlRun).where(CrawlRun.status == "running")
        )
    ).scalar_one()
    completed = (
        await session.execute(
            select(func.count()).select_from(CrawlRun).where(CrawlRun.status == "completed")
        )
    ).scalar_one()
    return AnalyticsOut(
        companies=companies,
        jobs=jobs,
        runs_in_progress=in_progress,
        runs_completed=completed,
    )


@router.get("/api/queue/status")
async def queue_status(request: Request) -> dict:
    queue = request.app.state.queue_manager
    return {
        "queue_size": queue.queue_size,
        "concurrency": queue.concurrency,
        "clients": request.app.state.event_hub.client_count,
    }


@router.get("/api/workflows")
async def workflows(session: AsyncSession = Depends(get_session)) -> list[dict]:
    result = await session.execute(select(Workflow).order_by(Workflow.updated_at.desc()).limit(200))
    rows = []
    for wf in result.scalars().all():
        rows.append(
            {
                "id": wf.id,
                "domain": wf.domain,
                "careers_url": wf.careers_url,
                "success_count": wf.success_count,
                "updated_at": wf.updated_at,
            }
        )
    return rows


@router.post("/api/export/csv")
async def export_csv(session: AsyncSession = Depends(get_session)) -> dict:
    result = await session.execute(select(Job).order_by(Job.created_at.desc()))
    jobs = result.scalars().all()
    rows = [
        {
            "company_id": j.company_id,
            "title": j.title,
            "location": j.location,
            "department": j.department,
            "employment_type": j.employment_type,
            "salary": j.salary,
            "visa_sponsorship": j.visa_sponsorship,
            "source_url": j.source_url,
            "apply_url": j.apply_url,
            "ats_provider": j.ats_provider,
            "created_at": j.created_at.isoformat(),
        }
        for j in jobs
    ]
    output_dir = Path("output")
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"platform_jobs_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"
    pd.DataFrame(rows).to_csv(path, index=False, encoding="utf-8-sig")
    return {"path": str(path), "count": len(rows)}


@router.get("/api/settings", response_model=SettingsOut)
async def get_settings(request: Request, session: AsyncSession = Depends(get_session)) -> SettingsOut:
    queue = request.app.state.queue_manager
    return SettingsOut(queue_concurrency=queue.concurrency)


@router.put("/api/settings", response_model=SettingsOut)
async def put_settings(payload: SettingsUpdate, session: AsyncSession = Depends(get_session)) -> SettingsOut:
    setting = await session.get(SettingsKV, "queue_concurrency")
    if setting is None:
        setting = SettingsKV(key="queue_concurrency", value=str(payload.queue_concurrency))
        session.add(setting)
    else:
        setting.value = str(payload.queue_concurrency)
    await session.commit()
    return SettingsOut(queue_concurrency=payload.queue_concurrency)


@router.websocket("/ws/events")
async def events_ws(websocket: WebSocket, request: Request) -> None:
    hub = request.app.state.event_hub
    await hub.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await hub.disconnect(websocket)
    except Exception:
        await hub.disconnect(websocket)
