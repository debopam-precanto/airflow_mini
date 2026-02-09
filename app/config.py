import os

API_KEY = os.getenv("AIRFLOW_MINI_API_KEY", "airflow-mini-secret-key")

DATABASE_PATH = os.getenv("AIRFLOW_MINI_DB_PATH", "airflow_mini.db")
DATABASE_URL = f"sqlite:///{DATABASE_PATH}"

MASTER_HOST = os.getenv("AIRFLOW_MINI_HOST", "127.0.0.1")
MASTER_PORT = int(os.getenv("AIRFLOW_MINI_PORT", "8000"))

WORKER_PORTS = [
    int(p) for p in os.getenv("AIRFLOW_MINI_WORKERS", "8001,8002").split(",")
]

SCHEDULER_INTERVAL = float(os.getenv("AIRFLOW_MINI_SCHEDULER_INTERVAL", "2.0"))
