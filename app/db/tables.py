from sqlalchemy import Column, String, Integer, Text, ForeignKey
from app.db.database import Base


class Workflow(Base):
    __tablename__ = "workflows"

    id = Column(String, primary_key=True)
    definition = Column(Text, nullable=False)
    created_at = Column(String, nullable=False)


class WorkflowRun(Base):
    __tablename__ = "workflow_runs"

    id = Column(String, primary_key=True)
    workflow_id = Column(String, ForeignKey("workflows.id"), nullable=False)
    status = Column(String, nullable=False, default="PENDING")
    started_at = Column(String, nullable=False)
    finished_at = Column(String, nullable=True)


class TaskInstance(Base):
    __tablename__ = "task_instances"

    id = Column(String, primary_key=True)
    run_id = Column(String, ForeignKey("workflow_runs.id"), nullable=False)
    task_id = Column(String, nullable=False)
    command = Column(Text, nullable=False)
    status = Column(String, nullable=False, default="PENDING")
    retries_left = Column(Integer, nullable=False, default=0)
    max_retries = Column(Integer, nullable=False, default=0)
    started_at = Column(String, nullable=True)
    finished_at = Column(String, nullable=True)
    output = Column(Text, nullable=True)
    worker_id = Column(String, nullable=True)
