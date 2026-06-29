from __future__ import annotations

import json
from datetime import datetime
from typing import Any

import aiosqlite

from .config import SETTINGS


class Database:
    def __init__(self, db_path: str | None = None) -> None:
        self.db_path = db_path or SETTINGS.database_path

    async def init(self) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.executescript(
                """
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS jobs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url TEXT UNIQUE NOT NULL,
                    domain TEXT,
                    company TEXT,
                    job_title TEXT,
                    ats_type TEXT,
                    status TEXT,
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
                    duration_seconds REAL,
                    notes TEXT,
                    screenshot_before TEXT,
                    screenshot_after TEXT
                );

                CREATE TABLE IF NOT EXISTS recordings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    domain TEXT,
                    ats_type TEXT,
                    url_pattern TEXT,
                    script_json TEXT NOT NULL,
                    recorded_at TEXT,
                    success_count INTEGER DEFAULT 0,
                    fail_count INTEGER DEFAULT 0,
                    last_used TEXT,
                    avg_completion_time REAL,
                    notes TEXT,
                    UNIQUE(domain, ats_type)
                );

                CREATE TABLE IF NOT EXISTS token_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id INTEGER,
                    operation TEXT,
                    model TEXT,
                    input_tokens INTEGER,
                    output_tokens INTEGER,
                    cached_tokens INTEGER,
                    cost_usd REAL,
                    timestamp TEXT
                );
                """
            )
            await db.commit()

    async def insert_job(self, payload: dict[str, Any]) -> int:
        keys = list(payload.keys())
        values = [payload[k] for k in keys]
        placeholders = ",".join(["?"] * len(keys))
        query = f"INSERT OR IGNORE INTO jobs ({','.join(keys)}) VALUES ({placeholders})"
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute(query, values)
            await db.commit()
            return cur.lastrowid

    async def update_job(self, url: str, updates: dict[str, Any]) -> None:
        assignments = ", ".join([f"{k} = ?" for k in updates])
        values = [updates[k] for k in updates] + [url]
        query = f"UPDATE jobs SET {assignments} WHERE url = ?"
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(query, values)
            await db.commit()

    async def update_status(self, url: str, status: str, notes: str | None = None) -> None:
        updates: dict[str, Any] = {"status": status}
        if notes:
            updates["notes"] = notes
        if status == "submitted":
            updates["applied_at"] = datetime.utcnow().isoformat()
        await self.update_job(url, updates)

    async def get_all_jobs(self) -> list[dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute("SELECT * FROM jobs ORDER BY id DESC")
            return [dict(row) for row in await cur.fetchall()]

    async def get_job(self, job_id: int) -> dict[str, Any] | None:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
            row = await cur.fetchone()
            return dict(row) if row else None

    async def get_by_status(self, status: str) -> list[dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute("SELECT * FROM jobs WHERE status = ? ORDER BY id DESC", (status,))
            return [dict(row) for row in await cur.fetchall()]

    async def get_stats(self) -> dict[str, Any]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            totals = await db.execute_fetchone(
                """
                SELECT COUNT(*) total,
                       SUM(CASE WHEN status='submitted' THEN 1 ELSE 0 END) submitted,
                       SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END) failed,
                       SUM(CASE WHEN status='skipped' THEN 1 ELSE 0 END) skipped,
                       SUM(CASE WHEN replay_used=1 THEN 1 ELSE 0 END) replay_used,
                       COALESCE(SUM(cost_usd), 0) total_cost
                FROM jobs
                """
            )
            total = totals[0] or 0
            submitted = totals[1] or 0
            success_rate = (submitted / total * 100) if total else 0
            return {
                "total": total,
                "submitted": submitted,
                "failed": totals[2] or 0,
                "skipped": totals[3] or 0,
                "replay_used": totals[4] or 0,
                "total_cost": round(totals[5] or 0, 6),
                "success_rate": round(success_rate, 2),
            }

    async def get_daily_stats(self) -> list[dict[str, Any]]:
        query = """
        SELECT substr(applied_at, 1, 10) day,
               COUNT(*) applications,
               COALESCE(SUM(cost_usd), 0) cost
        FROM jobs
        WHERE applied_at IS NOT NULL
        GROUP BY day
        ORDER BY day DESC
        LIMIT 30
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(query)
            return [dict(row) for row in await cur.fetchall()]

    async def get_cost_breakdown(self) -> list[dict[str, Any]]:
        query = """
        SELECT operation, model, COALESCE(SUM(cost_usd), 0) cost,
               COALESCE(SUM(input_tokens), 0) input_tokens,
               COALESCE(SUM(output_tokens), 0) output_tokens,
               COALESCE(SUM(cached_tokens), 0) cached_tokens
        FROM token_log
        GROUP BY operation, model
        ORDER BY cost DESC
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(query)
            return [dict(row) for row in await cur.fetchall()]

    async def upsert_recording(
        self,
        *,
        domain: str,
        ats_type: str,
        url_pattern: str,
        script_json: dict[str, Any],
        avg_completion_time: float,
        notes: str | None = None,
    ) -> int:
        now = datetime.utcnow().isoformat()
        query = """
        INSERT INTO recordings(domain, ats_type, url_pattern, script_json, recorded_at, success_count, fail_count, last_used, avg_completion_time, notes)
        VALUES (?, ?, ?, ?, ?, 1, 0, ?, ?, ?)
        ON CONFLICT(domain, ats_type) DO UPDATE SET
            url_pattern=excluded.url_pattern,
            script_json=excluded.script_json,
            recorded_at=excluded.recorded_at,
            last_used=excluded.last_used,
            avg_completion_time=excluded.avg_completion_time,
            notes=excluded.notes
        """
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                query,
                (
                    domain,
                    ats_type,
                    url_pattern,
                    json.dumps(script_json),
                    now,
                    now,
                    avg_completion_time,
                    notes,
                ),
            )
            await db.commit()
            cur = await db.execute(
                "SELECT id FROM recordings WHERE domain = ? AND ats_type = ?",
                (domain, ats_type),
            )
            row = await cur.fetchone()
            return int(row[0])

    async def get_recording_by_domain(self, domain: str) -> dict[str, Any] | None:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT * FROM recordings WHERE domain = ? AND success_count > 0 ORDER BY id DESC LIMIT 1",
                (domain,),
            )
            row = await cur.fetchone()
            return dict(row) if row else None

    async def get_recording_by_ats(self, ats_type: str) -> dict[str, Any] | None:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT * FROM recordings WHERE ats_type = ? AND success_count > 0 ORDER BY success_count DESC, id DESC LIMIT 1",
                (ats_type,),
            )
            row = await cur.fetchone()
            return dict(row) if row else None

    async def list_recordings(self) -> list[dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute("SELECT * FROM recordings ORDER BY last_used DESC, id DESC")
            rows = [dict(row) for row in await cur.fetchall()]
            for row in rows:
                script = json.loads(row["script_json"])
                success = row["success_count"] or 0
                fail = row["fail_count"] or 0
                row["success_rate"] = round((success / (success + fail) * 100), 2) if (success + fail) else 0
                row["steps"] = len(script.get("steps", []))
                row["status"] = "stale" if fail > 3 else "fresh"
            return rows

    async def increment_success(self, recording_id: int) -> None:
        query = """
        UPDATE recordings
        SET success_count = success_count + 1,
            last_used = ?
        WHERE id = ?
        """
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(query, (datetime.utcnow().isoformat(), recording_id))
            await db.commit()

    async def increment_fail(self, recording_id: int) -> None:
        query = "UPDATE recordings SET fail_count = fail_count + 1, last_used = ? WHERE id = ?"
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(query, (datetime.utcnow().isoformat(), recording_id))
            await db.commit()

    async def insert_token_log(
        self,
        *,
        job_id: int | None,
        operation: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cached_tokens: int,
        cost_usd: float,
    ) -> None:
        query = """
        INSERT INTO token_log(job_id, operation, model, input_tokens, output_tokens, cached_tokens, cost_usd, timestamp)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                query,
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
            row = await db.execute_fetchone("SELECT COALESCE(SUM(cost_usd), 0) FROM token_log")
            return float(row[0] or 0)

    async def get_savings_from_cache(self) -> float:
        # Approximation: cached tokens billed at 10%, so saving is 90% token-equivalent cost.
        query = "SELECT COALESCE(SUM(cached_tokens), 0) FROM token_log"
        async with aiosqlite.connect(self.db_path) as db:
            row = await db.execute_fetchone(query)
            return float(row[0] or 0)

    async def get_savings_from_replay(self) -> dict[str, float]:
        query = """
        SELECT COUNT(*) replay_count
        FROM jobs
        WHERE replay_used = 1 AND status = 'submitted'
        """
        async with aiosqlite.connect(self.db_path) as db:
            row = await db.execute_fetchone(query)
            replay_count = int(row[0] or 0)
            estimated_cost_saved = replay_count * 0.001
            return {"replay_count": replay_count, "estimated_cost_saved": estimated_cost_saved}
