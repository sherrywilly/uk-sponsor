from __future__ import annotations

import asyncio
from collections import deque
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from .agent import JobAgent
from .config import SETTINGS
from .database import Database

app = FastAPI(title="AI Job Application Agent")
db = Database(SETTINGS.db_path)
agent = JobAgent(db)


class JobAddRequest(BaseModel):
    urls: list[str] = Field(default_factory=list)


class RetryRequest(BaseModel):
    profile: dict[str, Any] | None = None


class AgentState:
    def __init__(self) -> None:
        self.running = False
        self.paused = False
        self.queue: deque[str] = deque()
        self.concurrency = 1


state = AgentState()
connections: set[WebSocket] = set()


async def broadcast(event: dict[str, Any]) -> None:
    stale: list[WebSocket] = []
    for ws in connections:
        try:
            await ws.send_json(event)
        except Exception:  # noqa: BLE001
            stale.append(ws)
    for ws in stale:
        connections.discard(ws)


@app.on_event("startup")
async def startup() -> None:
    await db.init()


@app.websocket("/ws/live")
async def ws_live(ws: WebSocket) -> None:
    await ws.accept()
    connections.add(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        connections.discard(ws)


@app.get("/api/stats")
async def get_stats() -> dict[str, Any]:
    stats = await db.get_stats()
    stats["agent"] = {"running": state.running, "paused": state.paused, "queued": len(state.queue)}
    return stats


@app.get("/api/jobs")
async def get_jobs(status: str | None = None) -> list[dict[str, Any]]:
    jobs = await db.get_all_jobs()
    if status:
        return [j for j in jobs if j.get("status") == status]
    return jobs


@app.get("/api/jobs/{job_id}")
async def get_job(job_id: int) -> dict[str, Any]:
    job = await db.get_job_by_id(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@app.get("/api/recordings")
async def get_recordings() -> list[dict[str, Any]]:
    return await db.list_recordings()


@app.get("/api/tokens")
async def get_tokens() -> list[dict[str, Any]]:
    return await db.get_token_breakdown()


@app.get("/api/cost")
async def get_cost() -> dict[str, Any]:
    return {
        "breakdown": await db.get_cost_breakdown(),
        "total_cost": await db.get_total_cost(),
        "saved_by_cache": await db.get_savings_from_cache(),
        "saved_by_replay": await db.get_savings_from_replay(),
    }


@app.post("/api/jobs/add")
async def add_jobs(payload: JobAddRequest) -> dict[str, Any]:
    for url in payload.urls:
        state.queue.append(url)
        await db.insert_job({"url": url, "domain": "", "company": "", "job_title": "", "ats_type": "custom", "status": "queued"})
    await broadcast({"event": "queue_updated", "queued": len(state.queue)})
    return {"queued": len(state.queue)}


@app.post("/api/jobs/{job_id}/retry")
async def retry_job(job_id: int, payload: RetryRequest) -> dict[str, Any]:
    job = await db.get_job_by_id(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    state.queue.appendleft(job["url"])
    await db.update_job(job["url"], status="queued")
    await broadcast({"event": "job_retried", "job_id": job_id})
    return {"status": "queued"}


@app.post("/api/agent/start")
async def start_agent() -> dict[str, Any]:
    if state.running:
        return {"status": "already_running"}
    state.running = True
    state.paused = False
    asyncio.create_task(_run_queue_loop())
    await broadcast({"event": "agent_started"})
    return {"status": "running"}


@app.post("/api/agent/pause")
async def pause_agent() -> dict[str, Any]:
    state.paused = True
    await broadcast({"event": "agent_paused"})
    return {"status": "paused"}


@app.get("/api/agent/status")
async def agent_status() -> dict[str, Any]:
    return {"running": state.running, "paused": state.paused, "queued": len(state.queue), "concurrency": state.concurrency}


async def _run_queue_loop() -> None:
    while state.running:
        if state.paused:
            await asyncio.sleep(0.5)
            continue
        if not state.queue:
            state.running = False
            await broadcast({"event": "agent_idle"})
            break
        url = state.queue.popleft()
        await broadcast({"event": "job_started", "url": url})
        result = await agent.process_job(url, SETTINGS.profile)
        await broadcast({"event": "job_completed", "url": url, "status": result.status, "replay_used": result.replay_used})
        await asyncio.sleep(0)
