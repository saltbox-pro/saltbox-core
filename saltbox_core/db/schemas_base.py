from pydantic import (
    BaseModel,
    Field,
    computed_field,
)
from taskiq import TaskiqResult
from taskiq.depends.progress_tracker import TaskState

from saltbox_core.config import SETTINGS


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
