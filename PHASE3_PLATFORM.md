# Phase 3 - Autonomous AI Recruitment Platform

## What was added

- Async FastAPI backend with WebSocket event streaming.
- Modular services for queueing, ATS detection, cache, workflow replay, and crawl orchestration.
- Persistent storage via SQLAlchemy (SQLite by default, PostgreSQL supported through `DATABASE_URL`).
- Job deduplication using stable `dedupe_hash` unique constraints.
- Action history persistence for every browser/tool step.
- Workflow replay from successful runs to reduce repeated LLM calls.
- React dashboard with all required pages:
  - Overview
  - Companies
  - Jobs
  - Live Browser
  - Agent Activity
  - Action History
  - Analytics
  - CSV Export
  - Settings

## Backend architecture

- `platform_backend/app.py`: FastAPI app, startup/shutdown lifecycle.
- `platform_backend/api/routes.py`: REST and WebSocket routes.
- `platform_backend/models.py`: Company, Job, CrawlRun, ActionEvent, Workflow, cache/settings tables.
- `platform_backend/services/crawl_orchestrator.py`: end-to-end crawl pipeline.
- `platform_backend/services/queue_manager.py`: configurable worker queue.
- `platform_backend/services/workflow_service.py`: save/replay workflow steps.
- `platform_backend/services/cache_service.py`: TTL cache for domain crawl outcomes.
- `platform_backend/services/ats_detector.py`: Greenhouse/Lever/Workday/Ashby/SmartRecruiters/BambooHR detection.
- `platform_backend/services/event_hub.py`: WebSocket pub/sub.

## Frontend architecture

- `platform_dashboard/`: Vite + React + TypeScript dashboard.
- `platform_dashboard/src/components/LiveFeed.tsx`: real-time WebSocket action feed.
- `platform_dashboard/src/pages/*`: dashboard pages.

## Run backend

```bash
pip install -r requirements.txt
python -m platform_backend.run_server
```

## Run with Docker (backend + dashboard)

```bash
docker compose up --build
```

Services:

- Backend API: `http://localhost:8000`
- Dashboard: `http://localhost:5173`

To run detached:

```bash
docker compose up --build -d
```

To stop:

```bash
docker compose down
```

## Run frontend

```bash
cd platform_dashboard
npm install
npm run dev
```

## Config

Environment variables:

- `DATABASE_URL` (default: `sqlite+aiosqlite:///./output/recruitment.db`)
- `QUEUE_CONCURRENCY` (default: `2`)
- `MAX_JOBS_PER_COMPANY` (default: `25`)
- `CACHE_TTL_SECONDS` (default: `86400`)

For PostgreSQL, example:

```bash
export DATABASE_URL='postgresql+psycopg://user:password@localhost:5432/recruitment'
```

With Docker Compose, override variables by exporting them in your shell before startup.
