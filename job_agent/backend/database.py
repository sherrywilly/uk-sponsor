from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiosqlite


UTC_NOW_SQL = "strftime('%Y-%m-%dT%H:%M:%fZ', 'now')"


@dataclass(slots=True)
class Database:
    path: Path

    async def connect(self) -> aiosqlite.Connection:
        conn = await aiosqlite.connect(self.path)
        conn.row_factory = aiosqlite.Row
        return conn

    async def init(self) -> None:
        async with await self.connect() as db:
            await db.executescript(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  url TEXT UNIQUE,
                  domain TEXT,
                  company TEXT,
                  job_title TEXT,
                  ats_type TEXT,
                  status TEXT,
                  applied_at TEXT,
                  jd_summary TEXT,
                  jd_keywords TEXT,
                  match_score REAL,
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
                  script_json TEXT,
                  recorded_at TEXT,
                  success_count INTEGER DEFAULT 0,
                  fail_count INTEGER DEFAULT 0,
                  last_used TEXT,
                  avg_completion_time REAL,
                  notes TEXT,
                  is_stale INTEGER DEFAULT 0,
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
                  timestamp TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
                );
                """
            )
            await db.commit()

    async def insert_job(self, payload: dict[str, Any]) -> int:
        async with await self.connect() as db:
            cursor = await db.execute(
                """
                INSERT INTO jobs(
                  url, domain, company, job_title, ats_type, status, applied_at, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(url) DO UPDATE SET
                  domain=excluded.domain,
                  company=excluded.company,
                  job_title=excluded.job_title,
                  ats_type=excluded.ats_type,
                  status=excluded.status,
                  notes=excluded.notes
                """,
                (
                    payload["url"],
                    payload.get("domain", ""),
                    payload.get("company", ""),
                    payload.get("job_title", ""),
                    payload.get("ats_type", "custom"),
                    payload.get("status", "queued"),
                    payload.get("applied_at", datetime.now(timezone.utc).isoformat()),
                    payload.get("notes", ""),
                ),
            )
            await db.commit()
            return cursor.lastrowid

    async def update_job(self, url: str, **kwargs: Any) -> None:
        if not kwargs:
            return
        fields = ", ".join(f"{k}=?" for k in kwargs.keys())
        values = list(kwargs.values()) + [url]
        async with await self.connect() as db:
            await db.execute(f"UPDATE jobs SET {fields} WHERE url=?", values)
            await db.commit()

    async def get_all_jobs(self) -> list[dict[str, Any]]:
        async with await self.connect() as db:
            rows = await db.execute_fetchall("SELECT * FROM jobs ORDER BY id DESC")
            return [dict(r) for r in rows]

    async def get_job_by_id(self, job_id: int) -> dict[str, Any] | None:
        async with await self.connect() as db:
            row = await db.execute_fetchone("SELECT * FROM jobs WHERE id=?", (job_id,))
            return dict(row) if row else None

    async def get_stats(self) -> dict[str, Any]:
        async with await self.connect() as db:
            total = await db.execute_fetchone("SELECT COUNT(*) AS c FROM jobs")
            submitted = await db.execute_fetchone("SELECT COUNT(*) AS c FROM jobs WHERE status='submitted'")
            skipped = await db.execute_fetchone("SELECT COUNT(*) AS c FROM jobs WHERE status='no_sponsorship'")
            replay_used = await db.execute_fetchone("SELECT COUNT(*) AS c FROM jobs WHERE replay_used=1")
            cost = await db.execute_fetchone("SELECT COALESCE(SUM(cost_usd),0) AS c FROM jobs")
        total_count = total["c"] if total else 0
        submitted_count = submitted["c"] if submitted else 0
        success_rate = (submitted_count / total_count * 100) if total_count else 0
        return {
            "total_applied": submitted_count,
            "total_jobs": total_count,
            "success_rate": round(success_rate, 2),
            "skipped": skipped["c"] if skipped else 0,
            "replay_used": replay_used["c"] if replay_used else 0,
            "cost_usd": round(cost["c"] if cost else 0, 6),
        }

    async def get_cost_breakdown(self) -> list[dict[str, Any]]:
        async with await self.connect() as db:
            rows = await db.execute_fetchall(
                """
                SELECT operation, COALESCE(SUM(cost_usd),0) AS cost
                FROM token_log
                GROUP BY operation
                ORDER BY cost DESC
                """
            )
            return [dict(r) for r in rows]

    async def upsert_recording(
        self,
        *,
        domain: str,
        ats_type: str,
        url_pattern: str,
        script_json: dict[str, Any],
        completion_time: float | None = None,
    ) -> int:
        now = datetime.now(timezone.utc).isoformat()
        async with await self.connect() as db:
            existing = await db.execute_fetchone(
                "SELECT id, success_count, avg_completion_time FROM recordings WHERE domain=? AND ats_type=?",
                (domain, ats_type),
            )
            if existing:
                await db.execute(
                    """
                    UPDATE recordings
                    SET url_pattern=?, script_json=?, recorded_at=?, last_used=?, notes=NULL,
                        is_stale=0
                    WHERE id=?
                    """,
                    (url_pattern, json.dumps(script_json), now, now, existing["id"]),
                )
                rec_id = existing["id"]
            else:
                cursor = await db.execute(
                    """
                    INSERT INTO recordings(domain, ats_type, url_pattern, script_json, recorded_at, success_count,
                                           fail_count, last_used, avg_completion_time, notes, is_stale)
                    VALUES (?, ?, ?, ?, ?, 0, 0, ?, ?, NULL, 0)
                    """,
                    (
                        domain,
                        ats_type,
                        url_pattern,
                        json.dumps(script_json),
                        now,
                        now,
                        completion_time,
                    ),
                )
                rec_id = cursor.lastrowid
            await db.commit()
            return rec_id

    async def get_recording_by_domain(self, domain: str) -> dict[str, Any] | None:
        async with await self.connect() as db:
            row = await db.execute_fetchone(
                """
                SELECT * FROM recordings
                WHERE domain=? AND success_count>0 AND is_stale=0
                ORDER BY success_count DESC, recorded_at DESC LIMIT 1
                """,
                (domain,),
            )
            return dict(row) if row else None

    async def get_recording_by_ats(self, ats_type: str) -> dict[str, Any] | None:
        async with await self.connect() as db:
            row = await db.execute_fetchone(
                """
                SELECT * FROM recordings
                WHERE ats_type=? AND success_count>0 AND is_stale=0
                ORDER BY success_count DESC, recorded_at DESC LIMIT 1
                """,
                (ats_type,),
            )
            return dict(row) if row else None

    async def list_recordings(self) -> list[dict[str, Any]]:
        async with await self.connect() as db:
            rows = await db.execute_fetchall("SELECT * FROM recordings ORDER BY last_used DESC")
            return [dict(r) for r in rows]

    async def increment_recording_success(self, recording_id: int, completion_time: float | None = None) -> None:
        async with await self.connect() as db:
            row = await db.execute_fetchone(
                "SELECT success_count, avg_completion_time FROM recordings WHERE id=?",
                (recording_id,),
            )
            if not row:
                return
            success_count = (row["success_count"] or 0) + 1
            avg = row["avg_completion_time"] or 0
            if completion_time is not None:
                avg = ((avg * (success_count - 1)) + completion_time) / success_count
            await db.execute(
                """
                UPDATE recordings
                SET success_count=?, last_used=?, avg_completion_time=?, is_stale=0
                WHERE id=?
                """,
                (success_count, datetime.now(timezone.utc).isoformat(), avg, recording_id),
            )
            await db.commit()

    async def increment_recording_fail(self, recording_id: int) -> None:
        async with await self.connect() as db:
            row = await db.execute_fetchone("SELECT fail_count FROM recordings WHERE id=?", (recording_id,))
            if not row:
                return
            fail_count = (row["fail_count"] or 0) + 1
            is_stale = 1 if fail_count > 3 else 0
            await db.execute(
                "UPDATE recordings SET fail_count=?, is_stale=? WHERE id=?",
                (fail_count, is_stale, recording_id),
            )
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
        async with await self.connect() as db:
            await db.execute(
                """
                INSERT INTO token_log(job_id, operation, model, input_tokens, output_tokens, cached_tokens, cost_usd)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (job_id, operation, model, input_tokens, output_tokens, cached_tokens, cost_usd),
            )
            await db.commit()

    async def get_token_breakdown(self) -> list[dict[str, Any]]:
        async with await self.connect() as db:
            rows = await db.execute_fetchall(
                """
                SELECT operation,
                       COALESCE(SUM(input_tokens),0) AS input_tokens,
                       COALESCE(SUM(output_tokens),0) AS output_tokens,
                       COALESCE(SUM(cached_tokens),0) AS cached_tokens,
                       COALESCE(SUM(cost_usd),0) AS cost_usd
                FROM token_log
                GROUP BY operation
                ORDER BY cost_usd DESC
                """
            )
            return [dict(r) for r in rows]

    async def get_total_cost(self) -> float:
        async with await self.connect() as db:
            row = await db.execute_fetchone("SELECT COALESCE(SUM(cost_usd),0) AS total FROM token_log")
            return float(row["total"] if row else 0)

    async def get_savings_from_cache(self) -> float:
        async with await self.connect() as db:
            row = await db.execute_fetchone(
                "SELECT COALESCE(SUM(cached_tokens * 0.0000008),0) AS saved FROM token_log"
            )
            return float(row["saved"] if row else 0)

    async def get_savings_from_replay(self) -> float:
        async with await self.connect() as db:
            row = await db.execute_fetchone(
                "SELECT COUNT(*) AS c FROM jobs WHERE replay_used=1 AND status='submitted'"
            )
            replay_count = row["c"] if row else 0
            return float(replay_count) * 0.001
