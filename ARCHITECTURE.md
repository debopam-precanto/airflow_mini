# Airflow Mini - Architecture

## Tech Stack

| Component       | Technology       | Why                                                    |
|-----------------|------------------|--------------------------------------------------------|
| Language        | Python 3.10+     | Best fit for scripting/orchestration systems           |
| Web Framework   | FastAPI          | Async, fast, auto-docs, Pydantic validation built-in  |
| Database        | SQLite + SQLAlchemy | Zero-setup persistence, survives restarts           |
| Workers         | Separate FastAPI processes | Explicit HTTP protocol, easy to reason about  |
| Task Execution  | subprocess       | Shell command execution with timeout support           |
| Auth            | API Key (static) | Simple, meets requirements, no RBAC needed             |

---

## High-Level Architecture

```
                         ┌──────────────────────────┐
                         │       Client / curl       │
                         └────────────┬─────────────┘
                                      │ HTTP + API Key
                                      ▼
                         ┌──────────────────────────┐
                         │     Web API (FastAPI)     │
                         │     Port: 8000            │
                         │                          │
                         │  POST /workflows         │
                         │  POST /workflows/{id}/run│
                         │  GET  /workflows/{id}    │
                         │  GET  /runs/{id}         │
                         │  GET  /runs/{id}/tasks   │
                         └────────────┬─────────────┘
                                      │
                                      ▼
                         ┌──────────────────────────┐
                         │       Scheduler           │
                         │                          │
                         │  - DAG validation        │
                         │  - Dependency resolution │
                         │  - Task dispatch (HTTP)  │
                         │  - Retry logic           │
                         │  - State tracking        │
                         └───┬──────────┬───────────┘
                             │          │
                    HTTP POST│          │HTTP POST
                   /execute  │          │/execute
                             ▼          ▼
                    ┌────────────┐ ┌────────────┐
                    │  Worker 1  │ │  Worker 2  │  ... N workers
                    │  Port:8001 │ │  Port:8002 │
                    │            │ │            │
                    │ subprocess │ │ subprocess │
                    │  execute   │ │  execute   │
                    └─────┬──────┘ └──────┬─────┘
                          │               │
                          │  HTTP callback │
                          └───────┬───────┘
                                  ▼
                         ┌──────────────────────────┐
                         │    SQLite Database        │
                         │    (airflow_mini.db)      │
                         └──────────────────────────┘
```

---

## Project Structure

```
airflow_mini/
├── app/
│   ├── __init__.py
│   ├── main.py                 # FastAPI app entry point & scheduler startup
│   ├── config.py               # Configuration (ports, DB path, API key, etc.)
│   │
│   ├── api/
│   │   ├── __init__.py
│   │   ├── routes.py           # All HTTP endpoint definitions
│   │   ├── schemas.py          # Pydantic request/response models
│   │   └── auth.py             # API key authentication dependency
│   │
│   ├── core/
│   │   ├── __init__.py
│   │   ├── dag.py              # DAG parsing, validation, cycle detection
│   │   ├── scheduler.py        # Scheduler: dispatch, retry, state transitions
│   │   └── models.py           # Task state enum & domain models
│   │
│   ├── worker/
│   │   ├── __init__.py
│   │   ├── server.py           # Worker FastAPI app (receives /execute requests)
│   │   └── executor.py         # Shell command execution via subprocess
│   │
│   └── db/
│       ├── __init__.py
│       ├── database.py         # SQLite engine & session management
│       ├── tables.py           # SQLAlchemy table definitions
│       └── repository.py      # CRUD operations (data access layer)
│
├── run_master.py               # Entry point: starts API server + scheduler
├── run_worker.py               # Entry point: starts a worker on a given port
├── requirements.txt
├── README.md
├── ARCHITECTURE.md
└── tests/
    ├── __init__.py
    ├── test_dag.py             # DAG validation & cycle detection tests
    ├── test_scheduler.py       # Scheduler logic tests
    ├── test_api.py             # API endpoint integration tests
    └── test_worker.py          # Worker execution tests
```

---

## Data Model (SQLite)

### Table: `workflows`

| Column     | Type    | Description                        |
|------------|---------|------------------------------------|
| id         | TEXT PK | Workflow identifier (user-defined) |
| definition | TEXT    | Full JSON definition of the DAG    |
| created_at | TEXT    | ISO timestamp                      |

### Table: `workflow_runs`

| Column      | Type    | Description                                    |
|-------------|---------|------------------------------------------------|
| id          | TEXT PK | UUID for this run                              |
| workflow_id | TEXT FK | References workflows.id                        |
| status      | TEXT    | PENDING / RUNNING / SUCCESS / FAILED           |
| started_at  | TEXT    | ISO timestamp                                  |
| finished_at | TEXT    | ISO timestamp (nullable)                       |

### Table: `task_instances`

| Column       | Type     | Description                                   |
|--------------|----------|-----------------------------------------------|
| id           | TEXT PK  | UUID for this task instance                   |
| run_id       | TEXT FK  | References workflow_runs.id                   |
| task_id      | TEXT     | Task identifier within the DAG               |
| command      | TEXT     | Shell command to execute                      |
| status       | TEXT     | PENDING / RUNNING / SUCCESS / FAILED / RETRYING |
| retries_left | INTEGER  | Remaining retries                             |
| max_retries  | INTEGER  | Original max_retries value                    |
| started_at   | TEXT     | ISO timestamp (nullable)                      |
| finished_at  | TEXT     | ISO timestamp (nullable)                      |
| output       | TEXT     | stdout/stderr capture (nullable)              |
| worker_id    | TEXT     | Which worker executed this (nullable)         |

### Task Definition Schema (Pydantic)

Each task in the workflow JSON must have:

| Field        | Type       | Required | Default | Description                    |
|--------------|------------|----------|---------|--------------------------------|
| id           | string     | Yes      | —       | Unique task identifier         |
| command      | string     | Yes      | —       | Shell command to execute       |
| dependencies | list[str]  | No       | `[]`    | List of task IDs this depends on |
| max_retries  | integer    | No       | `0`     | Number of retries on failure   |

---

## Task State Machine

```
                ┌─────────┐
                │ PENDING │
                └────┬────┘
                     │ dependencies met + worker available
                     ▼
                ┌─────────┐
                │ RUNNING │
                └────┬────┘
                     │
              ┌──────┴──────┐
              ▼              ▼
        ┌─────────┐    ┌─────────┐
        │ SUCCESS │    │  FAILED │
        └─────────┘    └────┬────┘
                            │ retries_left > 0?
                            ▼
                       ┌──────────┐
                       │ RETRYING │
                       └────┬─────┘
                            │ re-enqueue
                            ▼
                       ┌─────────┐
                       │ PENDING │ (retries_left decremented)
                       └─────────┘
```

---

## Execution Flow

1. **Register Workflow** — Client POSTs a DAG JSON to `/workflows`. The API validates it (checks for cycles, valid structure) and persists it to SQLite.

2. **Trigger Run** — Client POSTs to `/workflows/{id}/run`. The API creates a `workflow_run` record and `task_instance` records (one per task, all PENDING).

3. **Scheduler Loop** — A background async loop runs every 1-2 seconds:
   - Queries all active runs (status = RUNNING)
   - For each run, finds tasks whose dependencies are all SUCCESS and whose own status is PENDING
   - Dispatches these tasks to available workers via `POST /execute` (round-robin)
   - Updates task status to RUNNING

4. **Worker Execution** — The worker receives the task, runs the shell command via `subprocess.run()`, and sends back the result (success/failure + output) via an HTTP callback to the scheduler.

5. **Result Handling** — The scheduler processes the callback:
   - On success: marks task SUCCESS
   - On failure: if retries remain, marks RETRYING then re-enqueues as PENDING; otherwise marks FAILED
   - Checks if all tasks in the run are SUCCESS → marks run SUCCESS
   - Checks if any task is FAILED with no retries → marks run FAILED

---

## API Endpoints

| Method | Endpoint                  | Description                        | Auth Required |
|--------|---------------------------|------------------------------------|---------------|
| POST   | `/workflows`              | Register a new workflow (DAG)      | Yes           |
| GET    | `/workflows`              | List all registered workflows      | Yes           |
| GET    | `/workflows/{id}`         | Get workflow definition            | Yes           |
| POST   | `/workflows/{id}/run`     | Trigger a new run of the workflow  | Yes           |
| GET    | `/runs/{run_id}`          | Get run status                     | Yes           |
| GET    | `/runs/{run_id}/tasks`    | Get all task statuses for a run    | Yes           |
| POST   | `/internal/task-result`   | Worker callback to report task result (internal) | No (internal) |

---

## Authentication

- **Mechanism**: Static API Key passed via `X-API-Key` header
- **Configuration**: API key defined in `config.py` (or environment variable `AIRFLOW_MINI_API_KEY`)
- **Implementation**: FastAPI dependency that checks the header on every request
- **Default key for development**: auto-generated or configurable

---

## Worker Communication Protocol

**Scheduler → Worker** (dispatch task):
```
POST http://worker-host:port/execute
Content-Type: application/json

{
  "task_instance_id": "uuid",
  "task_id": "A",
  "command": "echo A",
  "callback_url": "http://scheduler-host:8000/internal/task-result"
}
```

**Worker → Scheduler** (report result):
```
POST http://scheduler-host:8000/internal/task-result
Content-Type: application/json

{
  "task_instance_id": "uuid",
  "status": "SUCCESS" | "FAILED",
  "output": "stdout/stderr content",
  "worker_id": "worker-8001"
}
```

---

## How to Run (Planned)

```bash
# Terminal 1: Start the master (API + Scheduler)
python run_master.py

# Terminal 2: Start worker 1
python run_worker.py --port 8001

# Terminal 3: Start worker 2
python run_worker.py --port 8002

# Register a workflow
curl -X POST http://localhost:8000/workflows \
  -H "X-API-Key: your-api-key" \
  -H "Content-Type: application/json" \
  -d '{"id": "example", "tasks": [...]}'

# Trigger a run
curl -X POST http://localhost:8000/workflows/example/run \
  -H "X-API-Key: your-api-key"

# Check run status
curl http://localhost:8000/runs/{run_id} \
  -H "X-API-Key: your-api-key"
```

---

## Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| FastAPI for both master & workers | Consistent HTTP interface, async support, auto-generated docs |
| SQLite for persistence | Zero-setup, file-based, sufficient for single-machine deployment |
| HTTP for scheduler-worker communication | Explicit, debuggable, matches the "explicit protocol" requirement |
| Callback-based result reporting | Workers push results back instead of scheduler polling — reduces latency |
| Background async scheduler loop | Non-blocking, runs alongside the API server in the same process |
| Round-robin worker dispatch | Simple, fair distribution; avoids complexity of load-based scheduling |

---

## Tradeoffs

| Tradeoff | Chosen Approach | Alternative |
|----------|----------------|-------------|
| Communication protocol | HTTP (simple, debuggable) | Message queue (more robust but heavier) |
| Worker discovery | Static config (list of worker ports) | Dynamic registration (more flexible but complex) |
| Scheduler model | Pull-based loop (poll DB every N seconds) | Event-driven (more responsive but complex) |
| Database | SQLite (simple, single-file) | PostgreSQL (better concurrency but requires setup) |
| Auth | Static API key | JWT tokens (more secure but unnecessary for scope) |
