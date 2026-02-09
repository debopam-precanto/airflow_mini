from pydantic import BaseModel, Field


# --- Request models ---

class TaskDefinition(BaseModel):
    id: str
    command: str
    dependencies: list[str] = Field(default_factory=list)
    max_retries: int = 0


class WorkflowCreate(BaseModel):
    id: str
    tasks: list[TaskDefinition]


# --- Response models ---

class WorkflowResponse(BaseModel):
    id: str
    definition: dict
    created_at: str


class RunResponse(BaseModel):
    id: str
    workflow_id: str
    status: str
    started_at: str
    finished_at: str | None = None


class TaskInstanceResponse(BaseModel):
    id: str
    run_id: str
    task_id: str
    command: str
    status: str
    retries_left: int
    max_retries: int
    started_at: str | None = None
    finished_at: str | None = None
    output: str | None = None
    worker_id: str | None = None


# --- Internal models ---

class TaskResultCallback(BaseModel):
    task_instance_id: str
    status: str
    output: str = ""
    worker_id: str = ""
