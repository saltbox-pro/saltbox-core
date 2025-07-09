from typing import Generic, TypeVar

from pydantic import (
    BaseModel,
    Field,
    computed_field,
)
from taskiq import TaskiqResult
from taskiq.depends.progress_tracker import TaskState

from salt_box_core.config import SETTINGS
from saltbox_bridge_messages import Iso8601ZDatetime as TimezoneAwareDatetime

__all__ = ['TimezoneAwareDatetime']

SchemaType = TypeVar('SchemaType', bound=BaseModel)


class CreatedModifiedMixin:
    created: TimezoneAwareDatetime = Field(title='Created')
    modified: TimezoneAwareDatetime = Field(title='Modified')


class PaginatedResponse(BaseModel, Generic[SchemaType]):
    total: int = Field(description='Total number of items', ge=0)
    data: list[SchemaType] = Field(description='Items list')


class CursoredResponse(BaseModel, Generic[SchemaType]):
    next_cursor: int = Field(description='Pointer to get next portion of data, 0 when no more data', ge=0)
    data: list[SchemaType] = Field(description='Items list')


class SkipLimitParams(BaseModel):
    skip: int = Field(default=0, ge=0)
    limit: int = Field(default=0, ge=0)


class AccessModel(BaseModel):
    roles: list[str] = Field(default=[])


class User(BaseModel):
    sub: str  # = Field(serialization_alias='id')
    resource_access: dict[str, AccessModel] | None = Field(default=None, exclude=True)
    email_verified: bool
    name: str
    email: str

    @computed_field  # type: ignore[prop-decorator]
    @property
    def roles(self) -> list[str]:
        client_roles: list[str] = []
        if self.resource_access:
            try:
                client_roles = self.resource_access[SETTINGS.keycloak_client].roles
            except KeyError:
                pass

        return client_roles


class UserShort(BaseModel):
    sub: str
    name: str
    email: str


class TaskiqTaskIdResponse(BaseModel):
    task_id: str = Field(title='Taskiq task ID')


class TaskiqTaskResult(TaskiqResult):
    task_id: str = Field(title='Taskiq task ID')
    progress: TaskState | None = Field(title='Task progress')
    progress_meta: str | None = Field(title='Task progress meta')
