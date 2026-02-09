import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.auth import verify_api_key
from app.api.schemas import (
    RunResponse,
    TaskInstanceResponse,
    TaskResultCallback,
    WorkflowCreate,
    WorkflowResponse,
)
from app.core.dag import validate_dag
from app.core.models import RunState, TaskState
from app.db import repository
from app.db.database import get_db

router = APIRouter()


# ── Public endpoints (require API key) ──────────────────────────────────────


@router.post(
    "/workflows",
    response_model=WorkflowResponse,
    dependencies=[Depends(verify_api_key)],
)
def register_workflow(workflow: WorkflowCreate, db: Session = Depends(get_db)):
    existing = repository.get_workflow(db, workflow.id)
    if existing:
        raise HTTPException(
            status_code=409, detail=f"Workflow '{workflow.id}' already exists"
        )

    definition = workflow.model_dump()
    errors = validate_dag(definition)
    if errors:
        raise HTTPException(status_code=400, detail={"errors": errors})

    wf = repository.create_workflow(db, workflow.id, definition)
    return WorkflowResponse(
        id=wf.id,
        definition=json.loads(wf.definition),
        created_at=wf.created_at,
    )


@router.get(
    "/workflows",
    response_model=list[WorkflowResponse],
    dependencies=[Depends(verify_api_key)],
)
def list_workflows(db: Session = Depends(get_db)):
    workflows = repository.list_workflows(db)
    return [
        WorkflowResponse(
            id=w.id,
            definition=json.loads(w.definition),
            created_at=w.created_at,
        )
        for w in workflows
    ]


@router.get(
    "/workflows/{workflow_id}",
    response_model=WorkflowResponse,
    dependencies=[Depends(verify_api_key)],
)
def get_workflow(workflow_id: str, db: Session = Depends(get_db)):
    wf = repository.get_workflow(db, workflow_id)
    if not wf:
        raise HTTPException(
            status_code=404, detail=f"Workflow '{workflow_id}' not found"
        )
    return WorkflowResponse(
        id=wf.id,
        definition=json.loads(wf.definition),
        created_at=wf.created_at,
    )


@router.post(
    "/workflows/{workflow_id}/run",
    response_model=RunResponse,
    dependencies=[Depends(verify_api_key)],
)
def trigger_run(workflow_id: str, db: Session = Depends(get_db)):
    wf = repository.get_workflow(db, workflow_id)
    if not wf:
        raise HTTPException(
            status_code=404, detail=f"Workflow '{workflow_id}' not found"
        )

    definition = json.loads(wf.definition)
    run = repository.create_run(db, workflow_id, definition["tasks"])
    return RunResponse(
        id=run.id,
        workflow_id=run.workflow_id,
        status=run.status,
        started_at=run.started_at,
    )


@router.get(
    "/runs/{run_id}",
    response_model=RunResponse,
    dependencies=[Depends(verify_api_key)],
)
def get_run(run_id: str, db: Session = Depends(get_db)):
    run = repository.get_run(db, run_id)
    if not run:
        raise HTTPException(
            status_code=404, detail=f"Run '{run_id}' not found"
        )
    return RunResponse(
        id=run.id,
        workflow_id=run.workflow_id,
        status=run.status,
        started_at=run.started_at,
        finished_at=run.finished_at,
    )


@router.get(
    "/runs/{run_id}/tasks",
    response_model=list[TaskInstanceResponse],
    dependencies=[Depends(verify_api_key)],
)
def get_task_instances(run_id: str, db: Session = Depends(get_db)):
    run = repository.get_run(db, run_id)
    if not run:
        raise HTTPException(
            status_code=404, detail=f"Run '{run_id}' not found"
        )

    tasks = repository.get_task_instances(db, run_id)
    return [
        TaskInstanceResponse(
            id=t.id,
            run_id=t.run_id,
            task_id=t.task_id,
            command=t.command,
            status=t.status,
            retries_left=t.retries_left,
            max_retries=t.max_retries,
            started_at=t.started_at,
            finished_at=t.finished_at,
            output=t.output,
            worker_id=t.worker_id,
        )
        for t in tasks
    ]


# ── Internal endpoint (worker callback, no auth) ───────────────────────────


@router.post("/internal/task-result")
def task_result_callback(result: TaskResultCallback, db: Session = Depends(get_db)):
    task = repository.get_task_instance(db, result.task_instance_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task instance not found")

    now = datetime.now(timezone.utc).isoformat()

    if result.status == TaskState.SUCCESS:
        repository.update_task_status(
            db,
            task.id,
            TaskState.SUCCESS,
            output=result.output,
            finished_at=now,
            worker_id=result.worker_id,
        )
    elif result.status == TaskState.FAILED:
        if task.retries_left > 0:
            # Mark as RETRYING — scheduler will move it back to PENDING
            repository.update_task_status(
                db,
                task.id,
                TaskState.RETRYING,
                output=result.output,
                finished_at=now,
                worker_id=result.worker_id,
            )
        else:
            repository.update_task_status(
                db,
                task.id,
                TaskState.FAILED,
                output=result.output,
                finished_at=now,
                worker_id=result.worker_id,
            )

    _check_run_completion(db, task.run_id)
    return {"status": "ok"}


def _check_run_completion(db: Session, run_id: str):
    """Check if all tasks in a run are finished and update run status."""
    tasks = repository.get_task_instances(db, run_id)
    statuses = [t.status for t in tasks]
    now = datetime.now(timezone.utc).isoformat()

    if all(s == TaskState.SUCCESS for s in statuses):
        repository.update_run_status(db, run_id, RunState.SUCCESS, finished_at=now)
    elif any(s == TaskState.FAILED for s in statuses):
        still_active = any(
            s in (TaskState.PENDING, TaskState.RUNNING, TaskState.RETRYING)
            for s in statuses
        )
        if not still_active:
            repository.update_run_status(
                db, run_id, RunState.FAILED, finished_at=now
            )
