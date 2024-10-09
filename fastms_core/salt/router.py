from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Form
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from fastms_core import http_errors
from fastms_core.config import SETTINGS

FormStr = Annotated[str, Form()]


router = APIRouter(
    prefix='/salt',
    tags=['Salt'],
    responses={404: {'description': 'Not found'}},
)


# Deprecated due to salt.auth.file method
@router.post('/auth', deprecated=True)
async def salt_auth_endpoint(username: FormStr, password: FormStr) -> JSONResponse:
    """For salt.auth.rest"""
    if username == SETTINGS.salt_username and password == SETTINGS.salt_password:
        acl = ['.*', '@wheel', '@jobs', '@runner']
        return JSONResponse(content=jsonable_encoder(acl))
    else:
        msg = f'Unknown user {username} or invalid password'
        raise http_errors.Unauthorized(msg)
