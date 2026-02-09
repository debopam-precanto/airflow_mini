import logging
import os
import threading

import httpx
from fastapi import FastAPI
from pydantic import BaseModel

from app.worker.executor import execute_command

logger = logging.getLogger(__name__)

app = FastAPI(title="Airflow Mini Worker")

WORKER_ID = os.getenv("WORKER_ID", "worker-unknown")


class ExecuteRequest(BaseModel):
    task_instance_id: str
    task_id: str
    command: str
    callback_url: str


@app.get("/health")
def health():
    return {"status": "ok", "worker_id": WORKER_ID}


@app.post("/execute")
def execute_task(request: ExecuteRequest):
    logger.info("[%s] Received task %s: %s", WORKER_ID, request.task_id, request.command)
    thread = threading.Thread(target=_run_and_report, args=(request,), daemon=True)
    thread.start()
    return {"status": "accepted", "worker_id": WORKER_ID}


def _run_and_report(request: ExecuteRequest):
    success, output = execute_command(request.command)
    status = "SUCCESS" if success else "FAILED"

    logger.info("[%s] Task %s finished: %s", WORKER_ID, request.task_id, status)

    payload = {
        "task_instance_id": request.task_instance_id,
        "status": status,
        "output": output,
        "worker_id": WORKER_ID,
    }

    try:
        httpx.post(request.callback_url, json=payload, timeout=10.0)
    except Exception as e:
        logger.error(
            "[%s] Callback failed for task %s: %s", WORKER_ID, request.task_id, e
        )
