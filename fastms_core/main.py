from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi_offline import FastAPIOffline

from fastms_core.config import APP_NAME, SETTINGS
from fastms_core.db.mongo.config import init_mongo
from fastms_core.db.redis import POOL
from fastms_core.jobs.router import router as jobs_router
from fastms_core.minions.consumer import GrainsConsumer
from fastms_core.minions.router import router as minions_router
from fastms_core.salt.router import router as salt_router
from fastms_core.tasks.router import router as task_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator:
    mongo_client = await init_mongo()
    consumer = GrainsConsumer(channel='grains')
    loop = asyncio.get_event_loop()
    task = loop.create_task(consumer.consume())
    yield
    task.cancel()
    mongo_client.close()
    await POOL.aclose()  # type: ignore[attr-defined]


APP = FastAPIOffline(title=APP_NAME, lifespan=lifespan)


APP.add_middleware(
    CORSMiddleware,
    allow_origins=SETTINGS.origins,
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

APP.include_router(minions_router)
APP.include_router(jobs_router)
APP.include_router(salt_router)
APP.include_router(task_router)
