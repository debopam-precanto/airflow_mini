import json
import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.models import RunState, TaskState
from app.db.tables import TaskInstance, Workflow, WorkflowRun


def create_workflow(db: Session, workflow_id: str, definition: dict) -> Workflow:
    workflow = Workflow(
        id=workflow_id,
        definition=json.dumps(definition),
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    db.add(workflow)
    db.commit()
    db.refresh(workflow)
    return workflow


def get_workflow(db: Session, workflow_id: str) -> Workflow | None:
    return db.query(Workflow).filter(Workflow.id == workflow_id).first()


def list_workflows(db: Session) -> list[Workflow]:
    return db.query(Workflow).all()


def create_run(db: Session, workflow_id: str, tasks: list[dict]) -> WorkflowRun:
    run_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    run = WorkflowRun(
        id=run_id,
        workflow_id=workflow_id,
        status=RunState.RUNNING,
        started_at=now,
    )
    db.add(run)

    for task in tasks:
        instance = TaskInstance(
            id=str(uuid.uuid4()),
            run_id=run_id,
            task_id=task["id"],
            command=task["command"],
            status=TaskState.PENDING,
            retries_left=task.get("max_retries", 0),
            max_retries=task.get("max_retries", 0),
        )
        db.add(instance)

    db.commit()
    db.refresh(run)
    return run


def get_run(db: Session, run_id: str) -> WorkflowRun | None:
    return db.query(WorkflowRun).filter(WorkflowRun.id == run_id).first()


def get_active_runs(db: Session) -> list[WorkflowRun]:
    return (
        db.query(WorkflowRun)
        .filter(WorkflowRun.status == RunState.RUNNING)
        .all()
    )


def update_run_status(
    db: Session, run_id: str, status: str, finished_at: str | None = None
):
    run = db.query(WorkflowRun).filter(WorkflowRun.id == run_id).first()
    if run:
        run.status = status
        if finished_at:
            run.finished_at = finished_at
        db.commit()


def get_task_instances(db: Session, run_id: str) -> list[TaskInstance]:
    return db.query(TaskInstance).filter(TaskInstance.run_id == run_id).all()


def get_task_instance(db: Session, task_instance_id: str) -> TaskInstance | None:
    return (
        db.query(TaskInstance).filter(TaskInstance.id == task_instance_id).first()
    )


def update_task_status(
    db: Session,
    task_instance_id: str,
    status: str,
    worker_id: str | None = None,
    output: str | None = None,
    started_at: str | None = None,
    finished_at: str | None = None,
    retries_left: int | None = None,
):
    task = (
        db.query(TaskInstance).filter(TaskInstance.id == task_instance_id).first()
    )
    if task:
        task.status = status
        if worker_id is not None:
            task.worker_id = worker_id
        if output is not None:
            task.output = output
        if started_at is not None:
            task.started_at = started_at
        if finished_at is not None:
            task.finished_at = finished_at
        if retries_left is not None:
            task.retries_left = retries_left
        db.commit()
