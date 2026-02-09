import argparse
import os

import uvicorn

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Start an Airflow Mini worker")
    parser.add_argument(
        "--port", type=int, default=8001, help="Port to run the worker on"
    )
    parser.add_argument(
        "--host", type=str, default="127.0.0.1", help="Host to bind to"
    )
    args = parser.parse_args()

    os.environ["WORKER_ID"] = f"worker-{args.port}"

    uvicorn.run(
        "app.worker.server:app",
        host=args.host,
        port=args.port,
        log_level="info",
    )
