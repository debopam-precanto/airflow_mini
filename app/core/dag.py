def validate_dag(definition: dict) -> list[str]:
    """Validate a workflow DAG definition. Returns a list of errors (empty = valid)."""
    errors = []

    if "id" not in definition:
        errors.append("Workflow must have an 'id' field")

    if "tasks" not in definition:
        errors.append("Workflow must have a 'tasks' field")
        return errors

    tasks = definition["tasks"]
    if not isinstance(tasks, list) or len(tasks) == 0:
        errors.append("'tasks' must be a non-empty list")
        return errors

    task_ids = set()
    for task in tasks:
        if "id" not in task:
            errors.append("Each task must have an 'id' field")
            continue
        if "command" not in task:
            errors.append(f"Task '{task['id']}' must have a 'command' field")
        if task["id"] in task_ids:
            errors.append(f"Duplicate task ID: '{task['id']}'")
        task_ids.add(task["id"])

    for task in tasks:
        if "id" not in task:
            continue
        for dep in task.get("dependencies", []):
            if dep not in task_ids:
                errors.append(
                    f"Task '{task['id']}' has unknown dependency: '{dep}'"
                )

    if not errors and _has_cycle(tasks):
        errors.append("Workflow contains a cycle")

    return errors


def _has_cycle(tasks: list[dict]) -> bool:
    """Detect cycles using DFS with three-color marking."""
    adj = {t["id"]: t.get("dependencies", []) for t in tasks}
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {tid: WHITE for tid in adj}

    def dfs(node):
        color[node] = GRAY
        for neighbor in adj[node]:
            if color[neighbor] == GRAY:
                return True
            if color[neighbor] == WHITE and dfs(neighbor):
                return True
        color[node] = BLACK
        return False

    for node in adj:
        if color[node] == WHITE:
            if dfs(node):
                return True
    return False
