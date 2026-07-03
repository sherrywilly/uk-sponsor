from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from platform_backend.models import Workflow


class WorkflowService:
    async def get_for_domain(self, session: AsyncSession, domain: str) -> Workflow | None:
        result = await session.execute(select(Workflow).where(Workflow.domain == domain))
        return result.scalar_one_or_none()

    async def save_success_workflow(
        self,
        session: AsyncSession,
        *,
        domain: str,
        careers_url: str,
        actions: list[dict[str, Any]],
    ) -> None:
        result = await session.execute(select(Workflow).where(Workflow.domain == domain))
        existing = result.scalar_one_or_none()
        serialized = json.dumps(actions, ensure_ascii=False)
        if existing:
            existing.careers_url = careers_url
            existing.actions_json = serialized
            existing.success_count += 1
        else:
            session.add(
                Workflow(
                    domain=domain,
                    careers_url=careers_url,
                    actions_json=serialized,
                    success_count=1,
                )
            )
        await session.commit()

    @staticmethod
    def parse_actions(workflow: Workflow) -> list[dict[str, Any]]:
        try:
            data = json.loads(workflow.actions_json)
            if isinstance(data, list):
                return [item for item in data if isinstance(item, dict)]
        except Exception:
            pass
        return []
