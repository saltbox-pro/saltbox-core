from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from fastms_core.minion_collections.schemas.filter_schemas import (
    MinionFilterSchema,
    MinionFilterValuesBody,
    UniqueGrainValuesResponse,
)
from fastms_core.minion_collections.schemas.minion_schemas import MinionSchema
from fastms_core.minion_collections.services.authz import MinionCollectionAuthzService, get_authz_service
from fastms_core.minion_collections.services.collection_service import MinionCollectionService, get_collection_service
from fastms_core.minion_collections.services.pipeline_builder import MongoPiplineBuilder
from fastms_core.utilities.model_schema import get_model_schema

router = APIRouter(prefix='/filters', tags=['Filters'])


@router.get('/schema', operation_id='filter_schema')
async def filter_schema() -> list[MinionFilterSchema]:
    return [MinionFilterSchema.model_validate(field) for field in get_model_schema(MinionSchema)]


@router.post('/unique-grain-values', operation_id='filter_values')
async def unique_field_values(
    body: MinionFilterValuesBody,
    authz_service: Annotated[MinionCollectionAuthzService, Depends(get_authz_service)],
    collection_service: Annotated[MinionCollectionService, Depends(get_collection_service)],
) -> UniqueGrainValuesResponse:
    """Get unique values for a field in the Minion model"""

    authz_result = await authz_service.check_access(
        input={
            'user': authz_service.user.model_dump(),
            'path': ['collections', body.collection_slug],
            'method': 'GET',
            'action': 'retrieve',
        }
    )

    if not authz_result.allow:
        raise HTTPException(status_code=403, detail='Not enough permissions')

    collection = await collection_service.get_by_slug(body.collection_slug)

    if not collection:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Collection not found')

    query = {'$and': [collection.query, body.query]}

    pipline_builder = MongoPiplineBuilder(body.field, query)
    pipline = pipline_builder.build()

    result = await collection_service.minion_pipeline(pipline)

    response = UniqueGrainValuesResponse(
        total=len(result),
        data=result,
    )

    return response
