import uvicorn

from app import config

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=config.MASTER_HOST,
        port=config.MASTER_PORT,
        log_level="info",
    )
