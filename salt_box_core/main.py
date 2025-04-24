from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.exception_handlers import http_exception_handler
from fastapi.middleware.cors import CORSMiddleware

from salt_box_core.config import APP_NAME, SETTINGS, logger
from salt_box_core.db.mongo.init_db import init_mongo_db
from salt_box_core.db.redis.config import POOL
from salt_box_core.jobs.routers.job_sc_router import router as job_schemas_router
from salt_box_core.jobs.routers.jobs_router import router as jobs_router
from salt_box_core.jobs.routers.jobs_router import ws_router as jobs_ws_router
from salt_box_core.masters.routers.master_route import router as masters_router
from salt_box_core.minion_collections.routers.collections_router import router as collections_router
from salt_box_core.minion_collections.routers.filters_router import router as filters_router
from salt_box_core.minion_collections.routers.minion_router import router as minions_router
from salt_box_core.pillars.routers.pillar_route import router as pillars_router
from salt_box_core.settings.routers.sls_repos_router import router as settings_sls_router
from salt_box_core.tasks.routers.tasks_router import router as task_router
from salt_box_core.tasks.routers.tasks_router import ws_router as task_ws_router
from salt_box_core.tasks.routers.template_router import router as template_router
from salt_box_core.tkq import broker


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator:
    await init_mongo_db()
    if not broker.is_worker_process:
        await broker.startup()

    yield
    await POOL.aclose()  # type: ignore[attr-defined]
    if not broker.is_worker_process:
        await broker.shutdown()


def _get_app() -> FastAPI:
    try:
        from fastapi_offline import FastAPIOffline

        app_t: FastAPI = FastAPIOffline(title=APP_NAME, lifespan=lifespan)
        logger.info('Using fastapi_offline to provide extra static')
    except ModuleNotFoundError:
        app_t = FastAPI(title=APP_NAME, lifespan=lifespan)
        logger.warning('fastapi_offline not found')

    return app_t


app = _get_app()


app.add_middleware(
    CORSMiddleware,
    allow_origins=SETTINGS.origins,
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)


@app.exception_handler(HTTPException)
async def logged_http_exception_handler(request: Request, exc: HTTPException) -> Response:
    """Custom exception handler for HTTP exceptions with logging"""
    logger.error(f'HTTP Exception: {request.url.path}: {exc}', exc_info=True)
    return await http_exception_handler(request, exc)


app.include_router(filters_router)
app.include_router(jobs_router)
app.include_router(job_schemas_router)
app.include_router(jobs_ws_router)
app.include_router(template_router)
app.include_router(task_router)
app.include_router(task_ws_router)
app.include_router(collections_router)
app.include_router(minions_router)
app.include_router(masters_router)
app.include_router(pillars_router)
app.include_router(router=settings_sls_router, prefix='/settings', tags=['Settings'])
