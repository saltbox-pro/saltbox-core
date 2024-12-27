from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi_offline import FastAPIOffline

from fastms_core.collections.router import collections_router
from fastms_core.config import APP_NAME, SETTINGS
from fastms_core.db.mongo.config import init_mongo
from fastms_core.db.redis import POOL
from fastms_core.dependencies import RolesRequiredDependency
from fastms_core.jobs.router import router as jobs_router
from fastms_core.jobs.router import ws_router as jobs_ws_router
from fastms_core.minions.router import filters_router, minions_router
from fastms_core.salt.router import router as salt_router
from fastms_core.tasks.router import router as task_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator:
    mongo_client = await init_mongo()

    yield
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

APP.include_router(
    minions_router,
    dependencies=[Depends(RolesRequiredDependency(['default-roles-salt.box']))],
)
APP.include_router(
    collections_router,
    dependencies=[Depends(RolesRequiredDependency(['default-roles-salt.box']))],
)
APP.include_router(
    filters_router,
    dependencies=[Depends(RolesRequiredDependency(['default-roles-salt.box']))],
)
APP.include_router(
    jobs_router,
    dependencies=[Depends(RolesRequiredDependency(['default-roles-salt.box']))],
)
APP.include_router(jobs_ws_router)
APP.include_router(salt_router)
APP.include_router(
    task_router,
    dependencies=[Depends(RolesRequiredDependency(['default-roles-salt.box']))],
)
