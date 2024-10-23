from __future__ import annotations

import io
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import yaml
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi_offline import FastAPIOffline

from fastms_core.config import APP_NAME, SETTINGS
from fastms_core.db.mongo.config import init_mongo
from fastms_core.db.redis import POOL
from fastms_core.jobs.router import router as jobs_router
from fastms_core.minions.router import router as minions_router
from fastms_core.salt.router import router as salt_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator:
    mongo_client = await init_mongo()
    yield
    mongo_client.close()
    await POOL.aclose()  # type: ignore[attr-defined]


APP = FastAPIOffline(
    title=APP_NAME,
    lifespan=lifespan,
    # TODO: does not work with nginx api/core/ redirect
    # swagger_ui_parameters={
    #     'url': 'openapi.yaml',
    # },
)

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


# https://github.com/fastapi/fastapi/discussions/7673
# TODO cache
@APP.get('/openapi.yaml', include_in_schema=False)
def read_openapi_yaml() -> Response:
    openapi_json = APP.openapi()
    yaml_s = io.StringIO()
    yaml.dump(openapi_json, yaml_s)
    return Response(yaml_s.getvalue(), media_type='text/yaml')
