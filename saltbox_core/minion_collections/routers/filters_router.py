from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from saltbox_core.minion_collections.schemas.filter_schemas import (
    MinionFilterSchema,
    MinionFilterValuesBody,
    UniqueGrainValuesResponse,
)
from saltbox_core.minion_collections.schemas.minion_schemas import MinionModel
from saltbox_core.minion_collections.services.collection_service import CollectionService, get_collection_service
from saltbox_core.minion_collections.services.minion_service import MinionService, get_minion_service
from saltbox_core.utilities.model_schema import get_model_schema
from saltbox_sdk.db.exceptions import ObjectNotFoundError

router = APIRouter(prefix='/filters', tags=['Filters'])


@router.get('/schema', operation_id='filter_schema')
async def filter_schema() -> list[MinionFilterSchema]:
    return [MinionFilterSchema(**field) for field in get_model_schema(MinionModel)]


@router.post('/unique-grain-values', operation_id='filter_values')
async def unique_field_values(
    body: MinionFilterValuesBody,
    collection_service: Annotated[CollectionService, Depends(get_collection_service)],
    minion_service: Annotated[MinionService, Depends(get_minion_service)],
) -> UniqueGrainValuesResponse:
    """Get unique values for a field in the Minion model"""
    try:
        collection = await collection_service.get_by_slug(body.collection_slug)
    except ObjectNotFoundError:
        msg = f"Collection '{body.collection_slug}' not found"
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg) from None

    query = {'$and': [collection.full_query, body.query]}

    result = await minion_service.get_unique_grain_values_by_field(
        field=body.field,
        query=query,
        skip=body.skip,
        limit=body.limit,
    )

    return result
