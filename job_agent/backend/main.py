from __future__ import annotations

import argparse
import asyncio
import csv

import uvicorn

from .agent import JobAgent
from .api import app, db
from .config import SETTINGS


async def run_batch(csv_path: str) -> None:
    await db.init()
    agent = JobAgent(db)
    with open(csv_path, newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            url = row.get("url") or row.get("job_url")
            if not url:
                continue
            result = await agent.process_job(url, SETTINGS.profile)
            print(f"{url} => {result.status} replay={result.replay_used} match={result.match_score}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", action="store_true", help="Run FastAPI server")
    parser.add_argument("--csv", type=str, default="", help="Run batch processing on CSV of URLs")
    parser.add_argument("--host", type=str, default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    if args.api:
        uvicorn.run(app, host=args.host, port=args.port)
        return

    if args.csv:
        asyncio.run(run_batch(args.csv))


if __name__ == "__main__":
    main()
