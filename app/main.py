import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import router
from app.core.scheduler import Scheduler
from app.db.database import init_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)

scheduler = Scheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    task = asyncio.create_task(scheduler.start())
    yield
    task.cancel()


app = FastAPI(title="Airflow Mini", lifespan=lifespan)
app.include_router(router)
