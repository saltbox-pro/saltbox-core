from __future__ import annotations

import asyncio
import datetime
import json
import logging

from contextlib import asynccontextmanager
from typing import Annotated, Any

import pydantic
import redis.exceptions as redis_exceptions

from fastapi import FastAPI, Form, WebSocket
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi_offline import FastAPIOffline
from fastms_core.jobs.router import router as jobs_router
from fastms_core.minions.router import router as minions_router

FormStr = Annotated[str, Form()]

SALT_CLIENT = SaltHttpClient(
    SETTINGS.salt_url,
    username=SETTINGS.salt_username,
    password=SETTINGS.salt_password,
    eauth=SETTINGS.salt_eauth,
    strict_ssl=False,)
LOGGER = logging.getLogger(__name__)

logging.config.dictConfig(LOG_CONFIG.dict())


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await POOL.aclose()


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
