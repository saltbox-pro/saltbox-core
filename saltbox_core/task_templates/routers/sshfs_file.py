from typing import Annotated

from fastapi import APIRouter, Depends

from saltbox_core.task_templates.schemas.sshfs_file import SshfsFileActions, SshfsFilePublicSchema
from saltbox_core.task_templates.services.sshfs_file import SshfsFileService, get_sshfs_file_service
from saltbox_sdk.db.mongo.schemas_base import PyObjectId
from saltbox_sdk.discovery_client.schemas import GatewayEndpointConfig

router = APIRouter(prefix='/source-files', tags=['Source Files'])


# @router.post(
#     '/list',
#     operation_id='sshfs_file_list',
#     openapi_extra=GatewayEndpointConfig(
#         policy='public',
#         action=SshfsFileActions.LIST,
#     ).model_dump(by_alias=True),
#     response_model=list[SshfsFilePublicSchema],
# )
# async def list_files(
#     source_id: PyObjectId,
#     service: Annotated[SshfsFileService, Depends(get_sshfs_file_service)],
# ) -> list[SshfsFilePublicSchema]:
#     files = await service.get_list(
#         query={'source_id': source_id}, skip=0, limit=0, projection_model=SshfsFilePublicSchema
#     )
#     return files
