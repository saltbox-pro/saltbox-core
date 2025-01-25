import logging.config
from typing import Annotated, Literal

import httpx
from fastapi import Depends, Request
from pydantic import BaseModel, ConfigDict

from fastms_core.config import LOG_CONFIG, SETTINGS
from fastms_core.db.mongo.schemas_base import User
from fastms_core.dependencies import get_current_user

logging.config.dictConfig(LOG_CONFIG.model_dump())

logger = logging.getLogger(__name__)


class OPAResult(BaseModel):
    allow: bool
    allowed_slugs: list[str] = []
    allowed_actions: list[str] = []

    model_config = ConfigDict(extra='allow')


class AuthzResponse(BaseModel):
    decision_id: str
    result: OPAResult | bool


class MinionCollectionAuthzService:
    def __init__(
        self,
        user: User,
        request: Request,
    ) -> None:
        self.opa_url = f'{SETTINGS.opa_url}/v1/data/core/collections'
        self.user = user
        self.request = request

    def _prepare_input(self, action: str) -> dict:
        # path e.g. `/api/core/collections/slug/`
        path_list = [
            segment for segment in self.request.url.path.strip('/').split('/') if segment not in {'api', 'core'}
        ]
        return {
            'input': {
                'user': self.user.model_dump(),
                'path': path_list,
                'method': self.request.method,
                'action': action,
            }
        }

    async def _make_request(self, input_dict: dict, *, type: Literal['allow', 'deny'] | None = None) -> AuthzResponse:
        url = f'{self.opa_url}/{type}' if type else self.opa_url
        async with httpx.AsyncClient() as r:
            response = await r.post(url, json=input_dict)
            response.raise_for_status()
            logger.info('response.json(): %s', response.json())
            return AuthzResponse.model_validate(response.json())

    async def check_access(self, action: str) -> OPAResult:
        input_dict = self._prepare_input(action)
        authz_response = await self._make_request(input_dict)

        if not isinstance(authz_response.result, OPAResult):
            msg = 'Expected OPAResult, got bool'
            raise ValueError(msg)

        return authz_response.result

    async def allow(self, action: str) -> bool:
        input_dict = self._prepare_input(action)
        authz_response = await self._make_request(input_dict, type='allow')

        if not isinstance(authz_response.result, bool):
            msg = 'Expected bool, got OPAResult'
            raise ValueError(msg)

        return authz_response.result

    async def deny(self, action: str) -> bool:
        input_dict = self._prepare_input(action)
        authz_response = await self._make_request(input_dict, type='deny')

        if not isinstance(authz_response.result, bool):
            msg = 'Expected bool, got OPAResult'
            raise ValueError(msg)

        return authz_response.result


async def get_authz_service(
    request: Request, user: Annotated[User, Depends(get_current_user)]
) -> MinionCollectionAuthzService:
    return MinionCollectionAuthzService(user, request)
