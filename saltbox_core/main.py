from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from functools import partial
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from saltbox_core import __version__
from saltbox_core.config import APP_DESC, APP_NAME, SETTINGS
from saltbox_core.db.init_mongo_db import init_mongo_db
from saltbox_core.jobs.routers.job_sc_router import router as job_schemas_router
from saltbox_core.jobs.routers.jobs_router import router as jobs_router
from saltbox_core.masters.routers.master_route import router as masters_router
from saltbox_core.masters.routers.system_route import router as system_router
from saltbox_core.minion_collections.routers.collections_router import router as collections_router
from saltbox_core.minion_collections.routers.filters_router import router as filters_router
from saltbox_core.minion_collections.routers.minion_router import router as minions_router
from saltbox_core.pillars.routers.pillar_route import router as pillars_router
from saltbox_core.settings.routers.sls_repos_router import router as settings_sls_router
from saltbox_core.tasks.routers.tasks_router import router as task_router
from saltbox_core.tasks.routers.template_router import router as template_router
from saltbox_core.tkq import broker
from saltbox_core.utilities.httpx_client import HttpxClientSingletoneFactory
from saltbox_core.utilities.redis_cache import CustomRedisCache
from saltbox_sdk.config.discovery_config import DISCOVERY_SETTINGS
from saltbox_sdk.db.redis.config import POOL, get_redis_now
from saltbox_sdk.discovery_client.client import DiscoveryClient
from saltbox_sdk.discovery_client.schemas import HealthCheckResponse
from saltbox_sdk.exceptions import SaltBoxBaseException
from saltbox_sdk.fastapi_utils.custom_openapi import custom_openapi, patch_swagger_config
from saltbox_sdk.fastapi_utils.exception_handlers import custom_http_handler
from saltbox_sdk.fastapi_utils.promethes_metrics.exporter import PrometheusExporter


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator:
    await init_mongo_db()
    if not broker.is_worker_process:
        await broker.startup()

        discovery_client = DiscoveryClient(
            openapi_schema=app.openapi(),
            httpx_client=HttpxClientSingletoneFactory.get_instance(),
        )
        await discovery_client.register()

    yield
    await CustomRedisCache.clear_cache(get_redis_now())
    if not broker.is_worker_process:
        await broker.shutdown()
    await POOL.aclose()  # type: ignore[attr-defined]


app_config: dict[str, Any] = {
    'title': APP_NAME,
    'lifespan': lifespan,
    'version': __version__,
    'description': APP_DESC,
    'root_path': SETTINGS.base_url_root_path,
    'healthcheck_path': '/discovery/health',
    # 'docs_url': '/docs', # or None to disable
    # 'openapi_url': '/openapi.json', # or None to disable
}

app_config = patch_swagger_config(app_config)

app = FastAPI(**app_config)


app.add_middleware(
    CORSMiddleware,
    allow_origins=SETTINGS.origins,
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)
app.add_exception_handler(SaltBoxBaseException, custom_http_handler)
PrometheusExporter(app).expose_metrics()


@app.get('/discovery/health')
async def health_check() -> HealthCheckResponse:
    """Health check endpoint"""
    return HealthCheckResponse(
        status='ok',
        message=f'Instance of {DISCOVERY_SETTINGS.service_name} is running',
    )


app.include_router(filters_router)
app.include_router(jobs_router)
app.include_router(job_schemas_router)
app.include_router(template_router)
app.include_router(task_router)
app.include_router(collections_router)
app.include_router(minions_router)
app.include_router(masters_router)
app.include_router(system_router)
app.include_router(pillars_router)
app.include_router(router=settings_sls_router, prefix='/settings', tags=['Settings'])

app.openapi = partial(custom_openapi, app, app_config, servers=[{'url': SETTINGS.base_url_root_path}])  # type: ignore[method-assign]
