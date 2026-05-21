from typing import Annotated

from fastapi import APIRouter, Body, Depends, status

from saltbox_core.salt.schemas.salt_keys import (
    SaltKeyActions,
    SaltKeyListRequestBody,
    SaltKeyMinionWithStatus,
    SaltKeySetStatusRequestBody,
    SaltKeySetStatusToAllRequestBody,
    SaltKeyUpdateResultSchema,
)
from saltbox_core.salt.services.salt_key import SaltKeysService, get_salt_key_service
from saltbox_sdk.db.schemas_base import PaginatedResponse
from saltbox_sdk.discovery_client.schemas import GatewayEndpointConfig

router = APIRouter(prefix='/salt/keys', tags=['Salt keys'])


@router.post(
    '/list',
    operation_id='salt_keys_list',
    description='List all Salt keys',
    openapi_extra=GatewayEndpointConfig(
        policy='core.salt.keys.list',
        action=SaltKeyActions.LIST,
    ).model_dump(by_alias=True),
)
async def salt_keys_list(
    body: Annotated[SaltKeyListRequestBody, Body()],
    service: Annotated[SaltKeysService, Depends(get_salt_key_service)],
) -> PaginatedResponse[SaltKeyMinionWithStatus]:
    data = await service.list_keys(masters=body.masters, status=body.status)

    return PaginatedResponse(total=len(data), data=data)


@router.post(
    '/accept',
    operation_id='salt_keys_accept',
    description='Accept Salt keys by list of minions',
    openapi_extra=GatewayEndpointConfig(
        policy='core.salt.keys.action',
        action=SaltKeyActions.ACCEPT,
    ).model_dump(by_alias=True),
)
async def salt_keys_accept(
    body: Annotated[SaltKeySetStatusRequestBody, Body()],
    service: Annotated[SaltKeysService, Depends(get_salt_key_service)],
) -> SaltKeyUpdateResultSchema:
    return await service.accept_keys(minions=body.minions)


@router.post(
    '/accept_all_unaccepted',
    operation_id='salt_keys_accept_unaccepted',
    description='Accept all unaccepted Salt keys',
    openapi_extra=GatewayEndpointConfig(
        policy='core.salt.keys.action',
        action=SaltKeyActions.ACCEPT,
    ).model_dump(by_alias=True),
)
async def accept_all_unaccepted(
    body: Annotated[SaltKeySetStatusToAllRequestBody, Body()],
    service: Annotated[SaltKeysService, Depends(get_salt_key_service)],
) -> SaltKeyUpdateResultSchema:
    return await service.accept_all_keys(masters=body.masters)


@router.post(
    '/reject',
    operation_id='salt_keys_reject',
    description='Reject Salt keys by list of minions',
    openapi_extra=GatewayEndpointConfig(
        policy='core.salt.keys.action',
        action=SaltKeyActions.REJECT,
    ).model_dump(by_alias=True),
)
async def salt_keys_reject(
    body: Annotated[SaltKeySetStatusRequestBody, Body()],
    service: Annotated[SaltKeysService, Depends(get_salt_key_service)],
) -> SaltKeyUpdateResultSchema:
    return await service.reject_keys(minions=body.minions)


@router.post(
    '/reject_all_unaccepted',
    operation_id='salt_keys_reject_all_unaccepted',
    description='Reject all unaccepted Salt keys',
    openapi_extra=GatewayEndpointConfig(
        policy='core.salt.keys.action',
        action=SaltKeyActions.REJECT,
    ).model_dump(by_alias=True),
)
async def salt_keys_reject_all_unaccepted(
    body: Annotated[SaltKeySetStatusToAllRequestBody, Body()],
    service: Annotated[SaltKeysService, Depends(get_salt_key_service)],
) -> SaltKeyUpdateResultSchema:
    return await service.reject_all_keys(masters=body.masters)


@router.post(
    '/delete',
    operation_id='salt_keys_delete',
    description='Delete Salt keys by list of minions',
    status_code=status.HTTP_204_NO_CONTENT,
    openapi_extra=GatewayEndpointConfig(
        policy='core.salt.keys.action',
        action=SaltKeyActions.DELETE,
    ).model_dump(by_alias=True),
)
async def salt_keys_delete(
    body: Annotated[SaltKeySetStatusRequestBody, Body()],
    service: Annotated[SaltKeysService, Depends(get_salt_key_service)],
) -> None:
    await service.delete_keys(minions=body.minions)


@router.post(
    '/delete_all',
    operation_id='salt_keys_delete_all',
    description='Delete all Salt keys',
    status_code=status.HTTP_204_NO_CONTENT,
    openapi_extra=GatewayEndpointConfig(
        policy='core.salt.keys.action',
        action=SaltKeyActions.DELETE,
    ).model_dump(by_alias=True),
)
async def salt_keys_delete_all(
    body: Annotated[SaltKeySetStatusToAllRequestBody, Body()],
    service: Annotated[SaltKeysService, Depends(get_salt_key_service)],
) -> None:
    await service.delete_all_keys(masters=body.masters)
