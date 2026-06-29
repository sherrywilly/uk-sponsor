from __future__ import annotations

import asyncio
from collections import deque
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from .agent import JobAgent
from .database import Database
from .recorder import detect_ats, get_domain

app = FastAPI(title="AI Job Application Agent")
db = Database()
agent = JobAgent(db)


class AddJobsRequest(BaseModel):
    urls: list[str]


class AgentControlResponse(BaseModel):
    status: str


@dataclass(slots=True)
class AgentState:
    running: bool = False
    paused: bool = False
    concurrency: int = 1


state = AgentState()
queue: deque[dict[str, Any]] = deque()


class ConnectionManager:
    def __init__(self) -> None:
        self.clients: list[WebSocket] = []

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self.clients.append(ws)

    def disconnect(self, ws: WebSocket) -> None:
        if ws in self.clients:
            self.clients.remove(ws)

    async def broadcast(self, event: str, payload: dict[str, Any]) -> None:
        if not self.clients:
            return
        dead: list[WebSocket] = []
        for ws in self.clients:
            try:
                await ws.send_json({"event": event, "payload": payload})
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


manager = ConnectionManager()


async def worker_loop() -> None:
    while state.running:
        if state.paused:
            await asyncio.sleep(0.5)
            continue
        if not queue:
            state.running = False
            await manager.broadcast("agent_completed", {"status": "idle"})
            break

        item = queue.popleft()
        await manager.broadcast("job_started", item)
        result = await agent.process_job(item["job_id"], item["url"])
        await manager.broadcast("job_completed", {**item, "result": result.status, "replay_used": result.replay_used})


@app.on_event("startup")
async def startup() -> None:
    await db.init()


@app.websocket("/ws/live")
async def live_ws(ws: WebSocket) -> None:
    await manager.connect(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(ws)


@app.get("/api/stats")
async def get_stats() -> dict[str, Any]:
    stats = await db.get_stats()
    stats["daily"] = await db.get_daily_stats()
    return stats


@app.get("/api/jobs")
async def get_jobs(status: str | None = None) -> list[dict[str, Any]]:
    return await db.get_all_jobs(status)


@app.get("/api/jobs/{job_id}")
async def get_job(job_id: int) -> dict[str, Any]:
    job = await db.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@app.get("/api/recordings")
async def get_recordings() -> list[dict[str, Any]]:
    return await db.list_recordings()


@app.get("/api/tokens")
async def get_tokens() -> dict[str, Any]:
    stats = await db.get_stats()
    return {
        "input": stats["token_input"],
        "output": stats["token_output"],
        "cached": stats["token_cached"],
    }


@app.get("/api/cost")
async def get_cost() -> dict[str, Any]:
    return {
        "total_usd": await db.get_total_cost(),
        "by_operation": await db.get_cost_breakdown(),
        "saved_by_cache": await db.get_savings_from_cache(),
        "saved_by_replay": await db.get_savings_from_replay(),
    }


@app.post("/api/jobs/add")
async def add_jobs(payload: AddJobsRequest) -> dict[str, Any]:
    added = []
    for url in payload.urls:
        domain = get_domain(url)
        ats_type = detect_ats(url)
        job_id = await db.insert_job(url, domain=domain, company=domain, job_title="", ats_type=ats_type)
        queue.append({"job_id": job_id, "url": url})
        added.append(job_id)
    return {"added": added, "queue_size": len(queue)}


@app.post("/api/jobs/{job_id}/retry")
async def retry_job(job_id: int) -> dict[str, Any]:
    job = await db.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    queue.append({"job_id": job_id, "url": job["url"]})
    await db.update_status(job_id, "queued")
    return {"queued": job_id}


@app.post("/api/agent/start", response_model=AgentControlResponse)
async def start_agent() -> AgentControlResponse:
    if state.running:
        return AgentControlResponse(status="running")
    state.running = True
    state.paused = False
    asyncio.create_task(worker_loop())
    await manager.broadcast("agent_started", {"status": "running"})
    return AgentControlResponse(status="running")


@app.post("/api/agent/pause", response_model=AgentControlResponse)
async def pause_agent() -> AgentControlResponse:
    state.paused = True
    await manager.broadcast("agent_paused", {"status": "paused"})
    return AgentControlResponse(status="paused")


@app.get("/api/agent/status", response_model=AgentControlResponse)
async def agent_status() -> AgentControlResponse:
    if not state.running:
        return AgentControlResponse(status="idle")
    return AgentControlResponse(status="paused" if state.paused else "running")
