from fastapi import Request
from fastapi.responses import JSONResponse

from saltbox_core.config import logger


async def custom_http_handler(_: Request, exc: Exception) -> JSONResponse:
    logger.exception(f'{exc.__class__.__name__}: {getattr(exc, "detail", str(exc))}')
    return JSONResponse(
        status_code=getattr(exc, 'status_code', 500),
        content={
            # 'code': getattr(exc, "code", None),
            # 'title': getattr(exc, "title", None),
            'detail': getattr(exc, 'detail', str(exc)),
        },
    )
