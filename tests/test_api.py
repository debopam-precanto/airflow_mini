from app import config

API_KEY = config.API_KEY
HEADERS = {"X-API-Key": API_KEY}

SAMPLE_WORKFLOW = {
    "id": "test_wf",
    "tasks": [
        {"id": "A", "command": "echo A", "dependencies": []},
        {"id": "B", "command": "echo B", "dependencies": ["A"]},
        {"id": "C", "command": "echo C", "dependencies": ["A"]},
        {"id": "D", "command": "echo D", "dependencies": ["B", "C"]},
    ],
}


def test_auth_required(client):
    response = client.get("/workflows")
    assert response.status_code in (401, 403, 422)


def test_invalid_api_key(client):
    response = client.get("/workflows", headers={"X-API-Key": "wrong-key"})
    assert response.status_code == 401


def test_register_workflow(client):
    response = client.post("/workflows", json=SAMPLE_WORKFLOW, headers=HEADERS)
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == "test_wf"
    assert len(data["definition"]["tasks"]) == 4


def test_register_duplicate_workflow(client):
    client.post("/workflows", json=SAMPLE_WORKFLOW, headers=HEADERS)
    response = client.post("/workflows", json=SAMPLE_WORKFLOW, headers=HEADERS)
    assert response.status_code == 409


def test_register_invalid_dag_with_cycle(client):
    workflow = {
        "id": "bad_wf",
        "tasks": [
            {"id": "A", "command": "echo A", "dependencies": ["B"]},
            {"id": "B", "command": "echo B", "dependencies": ["A"]},
        ],
    }
    response = client.post("/workflows", json=workflow, headers=HEADERS)
    assert response.status_code == 400


def test_list_workflows(client):
    client.post("/workflows", json=SAMPLE_WORKFLOW, headers=HEADERS)
    response = client.get("/workflows", headers=HEADERS)
    assert response.status_code == 200
    assert len(response.json()) == 1


def test_get_workflow(client):
    client.post("/workflows", json=SAMPLE_WORKFLOW, headers=HEADERS)
    response = client.get("/workflows/test_wf", headers=HEADERS)
    assert response.status_code == 200
    assert response.json()["id"] == "test_wf"


def test_get_workflow_not_found(client):
    response = client.get("/workflows/nonexistent", headers=HEADERS)
    assert response.status_code == 404


def test_trigger_run(client):
    client.post("/workflows", json=SAMPLE_WORKFLOW, headers=HEADERS)
    response = client.post("/workflows/test_wf/run", headers=HEADERS)
    assert response.status_code == 200
    data = response.json()
    assert data["workflow_id"] == "test_wf"
    assert data["status"] == "RUNNING"
    assert data["id"] is not None


def test_trigger_run_not_found(client):
    response = client.post("/workflows/nonexistent/run", headers=HEADERS)
    assert response.status_code == 404


def test_get_run(client):
    client.post("/workflows", json=SAMPLE_WORKFLOW, headers=HEADERS)
    run_resp = client.post("/workflows/test_wf/run", headers=HEADERS)
    run_id = run_resp.json()["id"]

    response = client.get(f"/runs/{run_id}", headers=HEADERS)
    assert response.status_code == 200
    assert response.json()["status"] == "RUNNING"


def test_get_run_not_found(client):
    response = client.get("/runs/nonexistent", headers=HEADERS)
    assert response.status_code == 404


def test_get_run_tasks(client):
    client.post("/workflows", json=SAMPLE_WORKFLOW, headers=HEADERS)
    run_resp = client.post("/workflows/test_wf/run", headers=HEADERS)
    run_id = run_resp.json()["id"]

    response = client.get(f"/runs/{run_id}/tasks", headers=HEADERS)
    assert response.status_code == 200
    tasks = response.json()
    assert len(tasks) == 4
    assert all(t["status"] == "PENDING" for t in tasks)

    task_ids = {t["task_id"] for t in tasks}
    assert task_ids == {"A", "B", "C", "D"}


def test_task_result_callback(client):
    client.post("/workflows", json=SAMPLE_WORKFLOW, headers=HEADERS)
    run_resp = client.post("/workflows/test_wf/run", headers=HEADERS)
    run_id = run_resp.json()["id"]

    # Get task A's instance id
    tasks_resp = client.get(f"/runs/{run_id}/tasks", headers=HEADERS)
    task_a = next(t for t in tasks_resp.json() if t["task_id"] == "A")

    # Simulate worker callback
    callback = {
        "task_instance_id": task_a["id"],
        "status": "SUCCESS",
        "output": "A output",
        "worker_id": "worker-8001",
    }
    response = client.post("/internal/task-result", json=callback)
    assert response.status_code == 200

    # Verify task A is now SUCCESS
    tasks_resp = client.get(f"/runs/{run_id}/tasks", headers=HEADERS)
    task_a_updated = next(t for t in tasks_resp.json() if t["task_id"] == "A")
    assert task_a_updated["status"] == "SUCCESS"
    assert task_a_updated["output"] == "A output"
