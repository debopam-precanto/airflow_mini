from app.core.dag import validate_dag


def test_valid_dag():
    dag = {
        "id": "test",
        "tasks": [
            {"id": "A", "command": "echo A", "dependencies": []},
            {"id": "B", "command": "echo B", "dependencies": ["A"]},
            {"id": "C", "command": "echo C", "dependencies": ["A"]},
            {"id": "D", "command": "echo D", "dependencies": ["B", "C"]},
        ],
    }
    assert validate_dag(dag) == []


def test_valid_dag_without_optional_fields():
    dag = {
        "id": "test",
        "tasks": [
            {"id": "A", "command": "echo A"},
            {"id": "B", "command": "echo B", "dependencies": ["A"]},
        ],
    }
    assert validate_dag(dag) == []


def test_missing_workflow_id():
    dag = {"tasks": [{"id": "A", "command": "echo A"}]}
    errors = validate_dag(dag)
    assert any("'id'" in e for e in errors)


def test_missing_tasks():
    dag = {"id": "test"}
    errors = validate_dag(dag)
    assert any("'tasks'" in e for e in errors)


def test_empty_tasks():
    dag = {"id": "test", "tasks": []}
    errors = validate_dag(dag)
    assert any("non-empty" in e for e in errors)


def test_duplicate_task_ids():
    dag = {
        "id": "test",
        "tasks": [
            {"id": "A", "command": "echo A"},
            {"id": "A", "command": "echo B"},
        ],
    }
    errors = validate_dag(dag)
    assert any("Duplicate" in e for e in errors)


def test_missing_task_command():
    dag = {
        "id": "test",
        "tasks": [{"id": "A"}],
    }
    errors = validate_dag(dag)
    assert any("'command'" in e for e in errors)


def test_unknown_dependency():
    dag = {
        "id": "test",
        "tasks": [
            {"id": "A", "command": "echo A", "dependencies": ["Z"]},
        ],
    }
    errors = validate_dag(dag)
    assert any("unknown dependency" in e for e in errors)


def test_cycle_detection():
    dag = {
        "id": "test",
        "tasks": [
            {"id": "A", "command": "echo A", "dependencies": ["B"]},
            {"id": "B", "command": "echo B", "dependencies": ["A"]},
        ],
    }
    errors = validate_dag(dag)
    assert any("cycle" in e.lower() for e in errors)


def test_self_dependency_cycle():
    dag = {
        "id": "test",
        "tasks": [
            {"id": "A", "command": "echo A", "dependencies": ["A"]},
        ],
    }
    errors = validate_dag(dag)
    assert any("cycle" in e.lower() for e in errors)


def test_three_node_cycle():
    dag = {
        "id": "test",
        "tasks": [
            {"id": "A", "command": "echo A", "dependencies": ["C"]},
            {"id": "B", "command": "echo B", "dependencies": ["A"]},
            {"id": "C", "command": "echo C", "dependencies": ["B"]},
        ],
    }
    errors = validate_dag(dag)
    assert any("cycle" in e.lower() for e in errors)
