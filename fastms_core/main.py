import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from fastms_core.collections.router import collections_router
from fastms_core.config import APP_NAME, SETTINGS
from fastms_core.db.mongo.config import init_mongo
from fastms_core.db.redis import POOL
from fastms_core.jobs.router import router as jobs_router
from fastms_core.jobs.router import ws_router as jobs_ws_router
from fastms_core.minions.router import filters_router, minions_router
from fastms_core.tasks.router import router as task_router
from fastms_core.tasks.router import ws_router as task_ws_router

LOGGER = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator:
    mongo_client = await init_mongo()

    yield
    mongo_client.close()
    await POOL.aclose()  # type: ignore[attr-defined]


def _get_app() -> ...:
    try:
        from fastapi_offline import FastAPIOffline

        LOGGER.info('Using fastapi_offline to provide extra static')
    except ModuleNotFoundError:
        from fastapi import FastAPI

        app_t = FastAPI
        LOGGER.warning('fastapi_offline not found')
    else:
        app_t = FastAPIOffline
    finally:
        return app_t(title=APP_NAME, lifespan=lifespan)


APP = _get_app()


APP.add_middleware(
    CORSMiddleware,
    allow_origins=SETTINGS.origins,
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

APP.include_router(minions_router)
APP.include_router(collections_router)
APP.include_router(filters_router)
APP.include_router(jobs_router)
APP.include_router(jobs_ws_router)
APP.include_router(task_router)
APP.include_router(task_ws_router)
