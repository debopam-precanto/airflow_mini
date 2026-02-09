import asyncio
import json
import logging
from datetime import datetime, timezone

import httpx

from app import config
from app.core.models import TaskState
from app.db import repository
from app.db.database import SessionLocal

logger = logging.getLogger(__name__)


class Scheduler:
    def __init__(self):
        self.worker_urls = [
            f"http://127.0.0.1:{port}" for port in config.WORKER_PORTS
        ]
        self._worker_index = 0

    def _next_worker_url(self) -> str | None:
        if not self.worker_urls:
            return None
        url = self.worker_urls[self._worker_index % len(self.worker_urls)]
        self._worker_index += 1
        return url

    async def start(self):
        logger.info(
            "Scheduler started (interval: %ss, workers: %s)",
            config.SCHEDULER_INTERVAL,
            self.worker_urls,
        )
        while True:
            try:
                await self._tick()
            except Exception as e:
                logger.error("Scheduler tick error: %s", e)
            await asyncio.sleep(config.SCHEDULER_INTERVAL)

    async def _tick(self):
        db = SessionLocal()
        try:
            active_runs = repository.get_active_runs(db)
            for run in active_runs:
                await self._process_run(db, run)
        finally:
            db.close()

    async def _process_run(self, db, run):
        tasks = repository.get_task_instances(db, run.id)
        workflow = repository.get_workflow(db, run.workflow_id)
        definition = json.loads(workflow.definition)
        dep_map = {
            t["id"]: t.get("dependencies", []) for t in definition["tasks"]
        }

        # Build a mutable status map
        task_status = {t.task_id: t.status for t in tasks}

        # Move RETRYING tasks back to PENDING (with decremented retries)
        for task in tasks:
            if task.status == TaskState.RETRYING:
                repository.update_task_status(
                    db,
                    task.id,
                    TaskState.PENDING,
                    retries_left=task.retries_left - 1,
                    started_at=None,
                    finished_at=None,
                )
                task_status[task.task_id] = TaskState.PENDING

        # Find and dispatch runnable tasks
        for task in tasks:
            if task_status.get(task.task_id) != TaskState.PENDING:
                continue
            deps = dep_map.get(task.task_id, [])
            if all(task_status.get(d) == TaskState.SUCCESS for d in deps):
                await self._dispatch_task(db, task)
                task_status[task.task_id] = TaskState.RUNNING

    async def _dispatch_task(self, db, task):
        worker_url = self._next_worker_url()
        if not worker_url:
            logger.warning("No workers configured")
            return

        now = datetime.now(timezone.utc).isoformat()
        callback_url = (
            f"http://{config.MASTER_HOST}:{config.MASTER_PORT}"
            f"/internal/task-result"
        )

        # Mark as RUNNING before dispatching
        repository.update_task_status(
            db, task.id, TaskState.RUNNING, started_at=now, worker_id=worker_url
        )

        payload = {
            "task_instance_id": task.id,
            "task_id": task.task_id,
            "command": task.command,
            "callback_url": callback_url,
        }

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{worker_url}/execute", json=payload, timeout=5.0
                )
                if resp.status_code != 200:
                    logger.error(
                        "Worker %s rejected task: %s", worker_url, resp.text
                    )
                    repository.update_task_status(
                        db,
                        task.id,
                        TaskState.PENDING,
                        started_at=None,
                        worker_id=None,
                    )
        except httpx.HTTPError as e:
            logger.error("Failed to dispatch to %s: %s", worker_url, e)
            # Revert to PENDING so it gets picked up next tick
            repository.update_task_status(
                db,
                task.id,
                TaskState.PENDING,
                started_at=None,
                worker_id=None,
            )
