from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.exception_handlers import http_exception_handler
from fastapi.middleware.cors import CORSMiddleware

from salt_box_core import __version__
from salt_box_core.config import APP_DESC, APP_NAME, SETTINGS, logger
from salt_box_core.db.init_mongo_db import init_mongo_db
from salt_box_core.jobs.routers.job_sc_router import router as job_schemas_router
from salt_box_core.jobs.routers.jobs_router import router as jobs_router
from salt_box_core.jobs.routers.jobs_router import ws_router as jobs_ws_router
from salt_box_core.masters.routers.master_route import router as masters_router
from salt_box_core.masters.routers.system_route import router as system_router
from salt_box_core.minion_collections.routers.collections_router import router as collections_router
from salt_box_core.minion_collections.routers.filters_router import router as filters_router
from salt_box_core.minion_collections.routers.minion_router import router as minions_router
from salt_box_core.pillars.routers.pillar_route import router as pillars_router
from salt_box_core.settings.routers.sls_repos_router import router as settings_sls_router
from salt_box_core.tasks.routers.tasks_router import router as task_router
from salt_box_core.tasks.routers.tasks_router import ws_router as task_ws_router
from salt_box_core.tasks.routers.template_router import router as template_router
from salt_box_core.tkq import broker
from salt_box_core.utilities.gpg import SaltBoxCrypt
from salt_box_core.utilities.httpx_client import get_httpx_async_client
from salt_box_core.utilities.redis_cache import CustomRedisCache
from saltbox_sdk.config import SETTINGS as SDKSETTINGS
from saltbox_sdk.db.redis.config import POOL, get_redis_now
from saltbox_sdk.discovery_client.client import DiscoveryClient
from saltbox_sdk.discovery_client.schemas import HealthCheckResponse


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator:
    SaltBoxCrypt()

    await init_mongo_db()
    if not broker.is_worker_process:
        await broker.startup()

        discovery_client = DiscoveryClient(
            openapi_schema=app.openapi(),
            httpx_client=get_httpx_async_client(),
        )
        await discovery_client.register()

    yield
    await CustomRedisCache.clear_cache(get_redis_now())
    if not broker.is_worker_process:
        await broker.shutdown()
    await POOL.aclose()  # type: ignore[attr-defined]


app = FastAPI(
    title=APP_NAME,
    version=__version__,
    description=APP_DESC,
    lifespan=lifespan,
    root_path=SETTINGS.base_url_root_path,
    servers=[
        {'url': SETTINGS.base_url_root_path},
    ],
)


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
    logger.exception('HTTP Exception: %s: %s', request.url.path, exc, exc_info=True)
    return await http_exception_handler(request, exc)


@app.get('/discovery/health')
async def health_check() -> HealthCheckResponse:
    """Health check endpoint"""
    return HealthCheckResponse(
        status='ok',
        message=f'Instance of {SDKSETTINGS.service_name} is running',
    )


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
app.include_router(system_router)
app.include_router(pillars_router)
app.include_router(router=settings_sls_router, prefix='/settings', tags=['Settings'])
