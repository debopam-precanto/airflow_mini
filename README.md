A minimal workflow orchestration system that lets you define workflows as DAGs, execute tasks in parallel across multiple worker processes, handle retries, and persist state — all exposed via an authenticated REST API.

## Architecture

```
              Client (curl)
                  │
                  │  HTTP + X-API-Key
                  ▼
        ┌──────────────────┐
        │  Master (FastAPI) │ ← Port 8000
        │                  │
        │  • REST API       │
        │  • Scheduler      │──── polls every 2s
        │  • SQLite DB      │
        └────┬────────┬─────┘
             │        │
    HTTP POST│        │HTTP POST
   /execute  │        │/execute
             ▼        ▼
       ┌────────┐ ┌────────┐
       │Worker 1│ │Worker 2│  ← Separate processes
       │  :8001 │ │  :8002 │
       └───┬────┘ └───┬────┘
           │          │
           └────┬─────┘
                │ HTTP callback
                ▼
        /internal/task-result
```

## Execution Flow

**Step-by-step, what happens when you run a workflow:**

1. **Register** — `POST /workflows` with a DAG JSON → validated (cycle detection via DFS) → stored in SQLite.

2. **Trigger** — `POST /workflows/{id}/run` → creates a run record + one task instance per task (all `PENDING`).

3. **Schedule** — Every 2 seconds, the scheduler:
   - Finds all `RUNNING` workflow runs
   - For each run, checks which `PENDING` tasks have all dependencies in `SUCCESS`
   - Dispatches those tasks to workers via `POST /execute` (round-robin)
   - Marks dispatched tasks as `RUNNING`

4. **Execute** — The worker runs the shell command via `subprocess`, then POSTs the result back to `/internal/task-result`.

5. **Complete** — The callback handler:
   - Success → marks task `SUCCESS`
   - Failure + retries left → marks task `RETRYING` (scheduler will re-enqueue next tick)
   - Failure + no retries → marks task `FAILED`
   - When all tasks succeed → run marked `SUCCESS`
   - When a task fails permanently and nothing else is active → run marked `FAILED`

## Data Model

Three SQLite tables:

```
workflows              workflow_runs              task_instances
┌──────────────┐      ┌─────────────────┐        ┌──────────────────┐
│ id (PK)      │◄─────│ workflow_id (FK) │        │ id (PK)          │
│ definition   │      │ id (PK)         │◄───────│ run_id (FK)      │
│ created_at   │      │ status          │        │ task_id           │
└──────────────┘      │ started_at      │        │ command           │
                      │ finished_at     │        │ status            │
                      └─────────────────┘        │ retries_left      │
                                                 │ max_retries        │
                                                 │ started_at         │
                                                 │ finished_at        │
                                                 │ output             │
                                                 │ worker_id          │
                                                 └──────────────────┘
```

**Task State Machine:**

```
PENDING → RUNNING → SUCCESS
                  → FAILED (no retries left)
                  → RETRYING → PENDING (retries_left--)
```

## Design Decisions

| Decision | Why |
|----------|-----|
| **FastAPI** for master and workers | Consistent HTTP interface, async support, auto-generated API docs at `/docs` |
| **SQLite** for persistence | Zero-setup, file-based, meets the "survive restart" requirement without external services |
| **HTTP** between scheduler and workers | Explicit protocol (as required), easy to debug with curl/logs, clear request/response contracts |
| **Callback pattern** for results | Workers push results back via POST instead of scheduler polling — lower latency, simpler worker lifecycle |
| **Round-robin dispatch** | Simple and fair; avoids the complexity of load-aware scheduling for a mini system |
| **Background asyncio task** for scheduler | Runs in the same process as the API — no extra process management, non-blocking |
| **Static API key** auth | Simplest mechanism that meets the "authentication, not authorization" requirement |

## Tradeoffs

| Choice | Pro | Con |
|--------|-----|-----|
| HTTP over message queue | Simple, debuggable, no extra infra | No built-in delivery guarantees |
| SQLite over PostgreSQL | Zero setup, single file | Limited concurrent write throughput |
| Static worker config | Simple to reason about | Must restart master to add workers |
| Polling scheduler (every 2s) | Simple loop, easy to understand | Up to 2s delay before a task starts |
| API key over JWT | No token expiry logic needed | Single shared key for all clients |

## How To Run

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Start master (API + scheduler)
python3 run_master.py

# 3. Start workers
python3 run_worker.py --port 8001
python3 run_worker.py --port 8002

# 4. Register a workflow
curl -s -X POST http://localhost:8000/workflows \
  -H "X-API-Key: airflow-mini-secret-key" \
  -H "Content-Type: application/json" \
  -d '{
    "id": "example_workflow",
    "tasks": [
      {"id": "A", "command": "echo A", "dependencies": []},
      {"id": "B", "command": "echo B", "dependencies": ["A"]},
      {"id": "C", "command": "echo C", "dependencies": ["A"]},
      {"id": "D", "command": "echo D", "dependencies": ["B", "C"]}
    ]
  }'

# 5. Trigger a run
curl -s -X POST http://localhost:8000/workflows/example_workflow/run \
  -H "X-API-Key: airflow-mini-secret-key"

# 6. Check run status (use the run ID from step 5)
curl -s http://localhost:8000/runs/<run_id> \
  -H "X-API-Key: airflow-mini-secret-key"

# 7. Check task statuses
curl -s http://localhost:8000/runs/<run_id>/tasks \
  -H "X-API-Key: airflow-mini-secret-key"

# 8. Run tests
python3 -m pytest tests/ -v
```

### Environment Variables (all optional)

| Variable | Default | Description |
|----------|---------|-------------|
| `AIRFLOW_MINI_API_KEY` | `airflow-mini-secret-key` | API authentication key |
| `AIRFLOW_MINI_DB_PATH` | `airflow_mini.db` | SQLite database file path |
| `AIRFLOW_MINI_PORT` | `8000` | Master API port |
| `AIRFLOW_MINI_WORKERS` | `8001,8002` | Comma-separated worker ports |
| `AIRFLOW_MINI_SCHEDULER_INTERVAL` | `2.0` | Scheduler poll interval (seconds) |
