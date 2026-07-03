from __future__ import annotations

import asyncio
from dataclasses import dataclass

from loguru import logger

from platform_backend.services.crawl_orchestrator import CrawlOrchestrator


@dataclass(slots=True)
class QueueItem:
    company_name: str
    homepage_url: str


class CrawlQueueManager:
    def __init__(self, orchestrator: CrawlOrchestrator, concurrency: int) -> None:
        self._orchestrator = orchestrator
        self._concurrency = max(1, concurrency)
        self._queue: asyncio.Queue[QueueItem] = asyncio.Queue()
        self._workers: list[asyncio.Task] = []
        self._running = False

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        for idx in range(self._concurrency):
            self._workers.append(asyncio.create_task(self._worker(idx + 1)))

    async def stop(self) -> None:
        self._running = False
        for worker in self._workers:
            worker.cancel()
        self._workers.clear()

    async def submit(self, company_name: str, homepage_url: str) -> None:
        await self._queue.put(QueueItem(company_name=company_name, homepage_url=homepage_url))

    async def _worker(self, worker_id: int) -> None:
        logger.info("Queue worker {} started", worker_id)
        while True:
            item = await self._queue.get()
            try:
                await self._orchestrator.process_company(item.company_name, item.homepage_url)
            except Exception:
                logger.exception("Worker {} failed item {}", worker_id, item.homepage_url)
            finally:
                self._queue.task_done()

    @property
    def queue_size(self) -> int:
        return self._queue.qsize()

    @property
    def concurrency(self) -> int:
        return self._concurrency
