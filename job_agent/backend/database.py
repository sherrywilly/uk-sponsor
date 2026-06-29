from __future__ import annotations

import json
from datetime import datetime
from typing import Any

import aiosqlite

from .config import DB_PATH


class Database:
    def __init__(self, db_path: str | None = None) -> None:
        self.db_path = db_path or str(DB_PATH)

    async def init(self) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.executescript(
                """
                PRAGMA journal_mode=WAL;

                CREATE TABLE IF NOT EXISTS jobs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url TEXT NOT NULL UNIQUE,
                    domain TEXT,
                    company TEXT,
                    job_title TEXT,
                    ats_type TEXT,
                    status TEXT NOT NULL DEFAULT 'pending',
                    applied_at TEXT,
                    jd_summary TEXT,
                    jd_keywords TEXT,
                    match_score INTEGER,
                    cv_path TEXT,
                    cover_letter_path TEXT,
                    recording_id INTEGER,
                    replay_used INTEGER DEFAULT 0,
                    tokens_input INTEGER DEFAULT 0,
                    tokens_output INTEGER DEFAULT 0,
                    tokens_cached INTEGER DEFAULT 0,
                    cost_usd REAL DEFAULT 0,
                    duration_seconds REAL DEFAULT 0,
                    notes TEXT,
                    screenshot_before TEXT,
                    screenshot_after TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS recordings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    domain TEXT,
                    ats_type TEXT,
                    url_pattern TEXT,
                    script_json TEXT NOT NULL,
                    recorded_at TEXT NOT NULL,
                    success_count INTEGER DEFAULT 0,
                    fail_count INTEGER DEFAULT 0,
                    last_used TEXT,
                    avg_completion_time REAL DEFAULT 0,
                    notes TEXT,
                    stale INTEGER DEFAULT 0,
                    UNIQUE(domain, ats_type)
                );

                CREATE TABLE IF NOT EXISTS token_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id INTEGER,
                    operation TEXT NOT NULL,
                    model TEXT NOT NULL,
                    input_tokens INTEGER DEFAULT 0,
                    output_tokens INTEGER DEFAULT 0,
                    cached_tokens INTEGER DEFAULT 0,
                    cost_usd REAL DEFAULT 0,
                    timestamp TEXT NOT NULL,
                    FOREIGN KEY(job_id) REFERENCES jobs(id)
                );
                """
            )
            await db.commit()

    async def insert_job(self, url: str, domain: str, company: str = "", job_title: str = "", ats_type: str = "custom") -> int:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """
                INSERT INTO jobs(url, domain, company, job_title, ats_type, status)
                VALUES (?, ?, ?, ?, ?, 'queued')
                ON CONFLICT(url) DO UPDATE SET
                    domain=excluded.domain,
                    company=excluded.company,
                    job_title=excluded.job_title,
                    ats_type=excluded.ats_type,
                    updated_at=CURRENT_TIMESTAMP
                """,
                (url, domain, company, job_title, ats_type),
            )
            await db.commit()
            return cursor.lastrowid

    async def update_status(self, job_id: int, status: str, **kwargs: Any) -> None:
        payload = {
            "status": status,
            "updated_at": datetime.utcnow().isoformat(),
            **kwargs,
        }
        keys = list(payload.keys())
        set_clause = ", ".join(f"{k} = ?" for k in keys)
        values = [payload[k] for k in keys] + [job_id]
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(f"UPDATE jobs SET {set_clause} WHERE id = ?", values)
            await db.commit()

    async def get_all_jobs(self, status: str | None = None) -> list[dict[str, Any]]:
        query = "SELECT * FROM jobs"
        args: tuple[Any, ...] = ()
        if status:
            query += " WHERE status = ?"
            args = (status,)
        query += " ORDER BY id DESC"
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(query, args)
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

    async def get_job(self, job_id: int) -> dict[str, Any] | None:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def get_stats(self) -> dict[str, Any]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            totals = await (await db.execute(
                "SELECT COUNT(*) as total, SUM(CASE WHEN status='submitted' THEN 1 ELSE 0 END) as submitted, SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END) as failed, SUM(CASE WHEN status='skipped_no_sponsorship' THEN 1 ELSE 0 END) as skipped, SUM(CASE WHEN replay_used=1 THEN 1 ELSE 0 END) as replay_used, SUM(cost_usd) as cost_usd FROM jobs"
            )).fetchone()
            token_totals = await (await db.execute(
                "SELECT SUM(input_tokens) as input_tokens, SUM(output_tokens) as output_tokens, SUM(cached_tokens) as cached_tokens, SUM(cost_usd) as cost_usd FROM token_log"
            )).fetchone()
        total = totals["total"] or 0
        submitted = totals["submitted"] or 0
        return {
            "total": total,
            "submitted": submitted,
            "failed": totals["failed"] or 0,
            "skipped": totals["skipped"] or 0,
            "success_rate": round((submitted / total) * 100, 2) if total else 0,
            "replay_used": totals["replay_used"] or 0,
            "total_cost_usd": round(float(totals["cost_usd"] or 0), 6),
            "token_input": token_totals["input_tokens"] or 0,
            "token_output": token_totals["output_tokens"] or 0,
            "token_cached": token_totals["cached_tokens"] or 0,
        }

    async def get_daily_stats(self) -> list[dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT date(created_at) as day,
                       COUNT(*) as total,
                       SUM(CASE WHEN status='submitted' THEN 1 ELSE 0 END) as submitted,
                       SUM(cost_usd) as cost
                FROM jobs
                GROUP BY date(created_at)
                ORDER BY day DESC
                LIMIT 30
                """
            )
            rows = await cursor.fetchall()
            return [dict(r) for r in rows][::-1]

    async def get_cost_breakdown(self) -> list[dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT operation, SUM(cost_usd) as cost FROM token_log GROUP BY operation ORDER BY cost DESC"
            )
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

    async def upsert_recording(
        self,
        domain: str,
        ats_type: str,
        url_pattern: str,
        script_json: dict[str, Any],
        completion_seconds: float,
    ) -> int:
        now = datetime.utcnow().isoformat()
        payload = json.dumps(script_json)
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO recordings(domain, ats_type, url_pattern, script_json, recorded_at, success_count, last_used, avg_completion_time)
                VALUES(?, ?, ?, ?, ?, 1, ?, ?)
                ON CONFLICT(domain, ats_type) DO UPDATE SET
                    script_json=excluded.script_json,
                    recorded_at=excluded.recorded_at,
                    success_count=recordings.success_count + 1,
                    last_used=excluded.last_used,
                    avg_completion_time=((recordings.avg_completion_time * recordings.success_count) + excluded.avg_completion_time) / (recordings.success_count + 1),
                    stale=0
                """,
                (domain, ats_type, url_pattern, payload, now, now, completion_seconds),
            )
            await db.commit()
            cursor = await db.execute("SELECT id FROM recordings WHERE domain = ? AND ats_type = ?", (domain, ats_type))
            row = await cursor.fetchone()
            return int(row[0])

    async def get_recording_by_domain(self, domain: str) -> dict[str, Any] | None:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM recordings WHERE domain = ? AND success_count > 0 AND stale = 0 ORDER BY success_count DESC LIMIT 1",
                (domain,),
            )
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def get_recording_by_ats(self, ats_type: str) -> dict[str, Any] | None:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM recordings WHERE ats_type = ? AND success_count > 0 AND stale = 0 ORDER BY success_count DESC LIMIT 1",
                (ats_type,),
            )
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def list_recordings(self) -> list[dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM recordings ORDER BY last_used DESC NULLS LAST, id DESC")
            return [dict(r) for r in await cursor.fetchall()]

    async def increment_recording_success(self, recording_id: int) -> None:
        now = datetime.utcnow().isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE recordings SET success_count = success_count + 1, last_used = ?, stale = 0 WHERE id = ?",
                (now, recording_id),
            )
            await db.commit()

    async def increment_recording_fail(self, recording_id: int) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE recordings SET fail_count = fail_count + 1, stale = CASE WHEN fail_count + 1 > 3 THEN 1 ELSE stale END WHERE id = ?",
                (recording_id,),
            )
            await db.commit()

    async def insert_token_log(
        self,
        job_id: int | None,
        operation: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cached_tokens: int,
        cost_usd: float,
    ) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO token_log(job_id, operation, model, input_tokens, output_tokens, cached_tokens, cost_usd, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job_id,
                    operation,
                    model,
                    input_tokens,
                    output_tokens,
                    cached_tokens,
                    cost_usd,
                    datetime.utcnow().isoformat(),
                ),
            )
            await db.commit()

    async def get_total_cost(self) -> float:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("SELECT SUM(cost_usd) FROM token_log")
            row = await cursor.fetchone()
            return float(row[0] or 0)

    async def get_savings_from_cache(self) -> float:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("SELECT SUM(cached_tokens) FROM token_log")
            cached = (await cursor.fetchone())[0] or 0
            return float(cached) * 0.9

    async def get_savings_from_replay(self) -> float:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("SELECT COUNT(*) FROM jobs WHERE replay_used = 1")
            replay_count = (await cursor.fetchone())[0] or 0
            return replay_count * 0.001
