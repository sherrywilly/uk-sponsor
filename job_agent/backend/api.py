from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from .agent import JobAgent, run_batch
from .config import SETTINGS
from .database import Database


class JobAddRequest(BaseModel):
    urls: list[str] = Field(default_factory=list)


class AgentControl(BaseModel):
    concurrency: int = 1


class LiveHub:
    def __init__(self) -> None:
        self.connections: set[WebSocket] = set()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self.connections.add(ws)

    def disconnect(self, ws: WebSocket) -> None:
        self.connections.discard(ws)

    async def emit(self, event: str, payload: dict[str, Any]) -> None:
        message = {"event": event, "payload": payload, "timestamp": datetime.utcnow().isoformat()}
        for conn in list(self.connections):
            try:
                await conn.send_json(message)
            except Exception:  # noqa: BLE001
                self.disconnect(conn)


db = Database()
agent = JobAgent(db)
app = FastAPI(title="AI Job Application Agent", version="1.0.0")
hub = LiveHub()
queue: asyncio.Queue[str] = asyncio.Queue()
runner_task: asyncio.Task | None = None
agent_status = {"state": "idle", "concurrency": 1}


@app.on_event("startup")
async def startup() -> None:
    await db.init()


@app.websocket("/ws/live")
async def ws_live(ws: WebSocket) -> None:
    await hub.connect(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        hub.disconnect(ws)


@app.get("/api/stats")
async def get_stats():
    stats = await db.get_stats()
    savings = await db.get_savings_from_replay()
    return {**stats, **savings}


@app.get("/api/jobs")
async def list_jobs(status: str | None = None):
    if status:
        return await db.get_by_status(status)
    return await db.get_all_jobs()


@app.get("/api/jobs/{job_id}")
async def get_job(job_id: int):
    row = await db.get_job(job_id)
    if not row:
        raise HTTPException(status_code=404, detail="Job not found")
    return row


@app.get("/api/recordings")
async def recordings():
    return await db.list_recordings()


@app.get("/api/tokens")
async def tokens():
    return await db.get_cost_breakdown()


@app.get("/api/cost")
async def cost():
    breakdown = await db.get_cost_breakdown()
    total = await db.get_total_cost()
    cache_saved = await db.get_savings_from_cache()
    replay_saved = await db.get_savings_from_replay()
    return {
        "total_cost_usd": total,
        "cache_token_saved": cache_saved,
        "replay": replay_saved,
        "breakdown": breakdown,
    }


@app.post("/api/jobs/add")
async def add_jobs(payload: JobAddRequest):
    for url in payload.urls:
        await queue.put(url)
        await db.insert_job({"url": url, "domain": "", "status": "queued"})
    await hub.emit("job_queued", {"count": len(payload.urls)})
    return {"queued": len(payload.urls)}


@app.post("/api/jobs/{job_id}/retry")
async def retry_job(job_id: int):
    row = await db.get_job(job_id)
    if not row:
        raise HTTPException(status_code=404, detail="Job not found")
    await queue.put(row["url"])
    await db.update_job(row["url"], {"status": "queued"})
    return {"queued": row["url"]}


async def _runner_loop() -> None:
    while agent_status["state"] == "running":
        url = await queue.get()
        await hub.emit("job_started", {"url": url})
        result = await agent.process_job(url, SETTINGS.candidate_profile)
        await hub.emit("job_completed", {"url": url, "result": result})
        queue.task_done()


@app.post("/api/agent/start")
async def start_agent(control: AgentControl):
    global runner_task
    if agent_status["state"] == "running":
        return {"status": "already_running"}

    agent_status["state"] = "running"
    agent_status["concurrency"] = max(1, min(5, control.concurrency))

    async def _run_concurrent() -> None:
        while agent_status["state"] == "running":
            batch = []
            while not queue.empty() and len(batch) < agent_status["concurrency"]:
                batch.append(await queue.get())
            if not batch:
                await asyncio.sleep(0.5)
                continue
            await hub.emit("job_started", {"batch": batch})
            results = await run_batch(agent, batch, SETTINGS.candidate_profile, agent_status["concurrency"])
            for url, result in zip(batch, results):
                await hub.emit("job_completed", {"url": url, "result": result})
                queue.task_done()

    runner_task = asyncio.create_task(_run_concurrent())
    return {"status": "running", "concurrency": agent_status["concurrency"]}


@app.post("/api/agent/pause")
async def pause_agent():
    global runner_task
    agent_status["state"] = "paused"
    if runner_task:
        runner_task.cancel()
        runner_task = None
    return {"status": "paused"}


@app.get("/api/agent/status")
async def agent_status_get():
    return {**agent_status, "queue_size": queue.qsize(), "host": SETTINGS.app_host, "port": SETTINGS.app_port}
