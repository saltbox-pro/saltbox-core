from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.exception_handlers import http_exception_handler
from fastapi.middleware.cors import CORSMiddleware

from salt_box_core import __version__
from salt_box_core.config import APP_DESC, APP_NAME, SETTINGS, logger
from salt_box_core.db.mongo.init_db import init_mongo_db
from salt_box_core.db.redis.config import POOL, get_redis_now
from salt_box_core.jobs.routers.job_sc_router import router as job_schemas_router
from salt_box_core.jobs.routers.jobs_router import router as jobs_router
from salt_box_core.jobs.routers.jobs_router import ws_router as jobs_ws_router
from salt_box_core.masters.routers.master_route import router as masters_router
from salt_box_core.masters.routers.system_route import router as system_router
from salt_box_core.middlwares import AuthMiddleware
from salt_box_core.minion_collections.routers.collections_router import router as collections_router
from salt_box_core.minion_collections.routers.filters_router import router as filters_router
from salt_box_core.minion_collections.routers.minion_router import router as minions_router
from salt_box_core.pillars.routers.pillar_route import router as pillars_router
from salt_box_core.settings.routers.sls_repos_router import router as settings_sls_router
from salt_box_core.tasks.routers.tasks_router import router as task_router
from salt_box_core.tasks.routers.tasks_router import ws_router as task_ws_router
from salt_box_core.tasks.routers.template_router import router as template_router
from salt_box_core.tkq import broker
from salt_box_core.utilities.custom_openapi import get_custom_openapi_schema
from salt_box_core.utilities.gpg import SaltBoxCrypt
from salt_box_core.utilities.redis_cache import CustomRedisCache


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator:
    SaltBoxCrypt()

    await init_mongo_db()
    if not broker.is_worker_process:
        await broker.startup()

    yield
    await CustomRedisCache.clear_cache(get_redis_now())
    await POOL.aclose()  # type: ignore[attr-defined]
    if not broker.is_worker_process:
        await broker.shutdown()


app_configs: dict[str, Any] = {
    'title': APP_NAME,
    'lifespan': lifespan,
    'version': __version__,
    'description': APP_DESC,
    'redoc_url': None,
    'swagger_ui_init_oauth': {
        'clientId': SETTINGS.keycloak_client,
        'clientSecret': SETTINGS.keycloak_client_secret,
        'scopes': 'openid',
    },
    'swagger_ui_parameters': {
        'displayRequestDuration': True,
        'filter': True,
    },
    'root_path': SETTINGS.base_url_root_path,
}

if not SETTINGS.show_docs:
    app_configs.update(
        {
            'docs_url': None,
            'openapi_url': None,
            'swagger_ui_init_oauth': None,
            'swagger_ui_parameters': None,
        }
    )

app = FastAPI(**app_configs)


app.add_middleware(
    CORSMiddleware,
    allow_origins=SETTINGS.origins,
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

_NO_AUTH_PATHS = [uri for uri in [app.docs_url, app.openapi_url, app.swagger_ui_oauth2_redirect_url] if uri]
_NO_AUTH_PATHS.append(r'/system/[\w-]+/authorized_keys')

app.add_middleware(
    AuthMiddleware,
    # Need add SETTINGS.base_url_root_path.rstrip('/') + uri in some cases
    excluded_paths=_NO_AUTH_PATHS
)


@app.exception_handler(HTTPException)
async def logged_http_exception_handler(request: Request, exc: HTTPException) -> Response:
    """Custom exception handler for HTTP exceptions with logging"""
    logger.exception(f'HTTP Exception: {request.url.path}: {exc}', exc_info=True)
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
app.include_router(system_router)
app.include_router(pillars_router)
app.include_router(router=settings_sls_router, prefix='/settings', tags=['Settings'])


if SETTINGS.show_docs:

    def custom_openapi() -> dict:
        if app.openapi_schema:
            return app.openapi_schema

        app.openapi_schema = get_custom_openapi_schema(
            app_configs=app_configs,
            routes=app.routes,
            servers=[{'url': SETTINGS.base_url_root_path}],
        )
        return app.openapi_schema

    app.openapi = custom_openapi  # type: ignore[method-assign]
