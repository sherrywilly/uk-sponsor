# Job Agent Docker Setup

## Prerequisites
- Docker Engine with Compose support
- A populated `job_agent/.env` file (copy from `.env.example`)

## Build and Run
From repository root:

```bash
docker compose up --build
```

## Services
- Backend API: `http://localhost:8000`
- Dashboard UI: `http://localhost:5173`

## Notes
- Runtime artifacts are persisted to local folders via bind mounts:
  - `job_agent/recordings`
  - `job_agent/screenshots`
  - `job_agent/cvs`
  - `job_agent/cover_letters`
  - `job_agent/logs`
- Ensure `ANTHROPIC_API_KEY` is present in `job_agent/.env` for Claude-backed features.
