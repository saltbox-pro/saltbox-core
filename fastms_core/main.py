from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from fastms_core.config import APP_NAME, SETTINGS, logger
from fastms_core.db.mongo.init_db import init_mongo_db
from fastms_core.db.redis import POOL
from fastms_core.jobs.router import router as jobs_router
from fastms_core.jobs.router import ws_router as jobs_ws_router
from fastms_core.minion_collections.routers.collections_router import router as collections_router
from fastms_core.minion_collections.routers.filters_router import router as filters_router
from fastms_core.minion_collections.routers.minion_router import router as minions_router
from fastms_core.tasks.router import router as task_router
from fastms_core.tasks.router import ws_router as task_ws_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator:
    await init_mongo_db()

    yield
    await POOL.aclose()  # type: ignore[attr-defined]


def _get_app() -> FastAPI:
    try:
        from fastapi_offline import FastAPIOffline

        app_t: FastAPI = FastAPIOffline(title=APP_NAME, lifespan=lifespan)
        logger.info('Using fastapi_offline to provide extra static')
    except ModuleNotFoundError:
        app_t = FastAPI(title=APP_NAME, lifespan=lifespan)
        logger.warning('fastapi_offline not found')

    return app_t


APP = _get_app()


APP.add_middleware(
    CORSMiddleware,
    allow_origins=SETTINGS.origins,
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

APP.include_router(filters_router)
APP.include_router(jobs_router)
APP.include_router(jobs_ws_router)
APP.include_router(task_router)
APP.include_router(task_ws_router)
APP.include_router(collections_router)
APP.include_router(minions_router)
