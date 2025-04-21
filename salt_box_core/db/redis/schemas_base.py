from typing import Annotated

from pydantic import AfterValidator, Field


def sortedset_id_validate(value: str) -> str:
    # TODO @: Validate this
    return value


SortedSetId = Annotated[str, AfterValidator(sortedset_id_validate)]


class IDMixin:
    id: SortedSetId = Field(title='ID')
