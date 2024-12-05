import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi_offline import FastAPIOffline

from fastms_core.config import APP_NAME, SETTINGS
from fastms_core.db.mongo.config import init_mongo
from fastms_core.db.redis import POOL
from fastms_core.dependencies import RolesRequiredDependency
from fastms_core.jobs.router import router as jobs_router
from fastms_core.jobs.router import ws_router as jobs_ws_router
from fastms_core.minions.consumer import GrainsConsumer
from fastms_core.minions.router import router as minions_router
from fastms_core.salt.router import router as salt_router
from fastms_core.tasks.router import router as task_router
from fastms_core.tasks.tasks_watcher import TasksWatcher


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator:
    mongo_client = await init_mongo()
    loop = asyncio.get_event_loop()

    # Grains consumer
    grains_consumer = GrainsConsumer(channel='grains')
    grains_consumer_task = loop.create_task(grains_consumer.consume())
    # Tasks watcher
    tasks_watcher = TasksWatcher()
    tasks_task_watcher = loop.create_task(tasks_watcher.process())

    yield
    grains_consumer_task.cancel()
    tasks_task_watcher.cancel()
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

APP.include_router(minions_router, dependencies=[Depends(RolesRequiredDependency(['default-roles-fastms']))])
APP.include_router(jobs_router, dependencies=[Depends(RolesRequiredDependency(['default-roles-fastms']))])
APP.include_router(jobs_ws_router)
APP.include_router(salt_router)
APP.include_router(task_router, dependencies=[Depends(RolesRequiredDependency(['default-roles-fastms']))])
