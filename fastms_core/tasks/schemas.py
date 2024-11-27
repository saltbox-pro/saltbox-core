from enum import Enum
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict, Field

from fastms_core.db.mongo.schemas_base import BaseDBSchema, PaginatedListQueryParams

# Task template schemas


class TaskTemplateVariable(BaseModel):
    class TaskTemplateType(str, Enum):
        string = 'str'
        integer = 'int'
        float = 'float'
        bool = 'bool'
        choices = 'choices'

    title: str = Field(title='Title')
    name: str = Field(title='Name')
    type: TaskTemplateType = Field(title='Type', default=TaskTemplateType.string)
    required: bool | None = Field(title='Required', default=True)
    choices: list[str | int | float] | None = Field(title='Choices')
    default_value: str | int | float | bool | None = Field(title='Default value')


class TaskTemplateBaseSchema(BaseModel):
    title: str = Field(title='Title')
    fun: str = Field(title='Salt fun')

    variables: list[TaskTemplateVariable] = Field(title='Variables')
    task_args: list[str] = Field(title='Args')
    task_kwargs: dict[str, Any] = Field(title='Kwargs')


class TaskTemplateDBSchema(BaseDBSchema, TaskTemplateBaseSchema):
    pass


class TaskTemplateSchema(TaskTemplateDBSchema):
    pass


class TaskTemplateCreateSchema(TaskTemplateBaseSchema):
    pass


class TaskTemplateUpdateSchema(TaskTemplateBaseSchema):
    pass


class TaskTemplateListSchema(TaskTemplateDBSchema):
    pass


class TaskTemplateListQueryParams(PaginatedListQueryParams):
    model_config: ClassVar[ConfigDict] = {'extra': 'forbid'}


# Tasks schemas


class TaskBaseSchema(BaseModel):
    class TaskStatus(str, Enum):
        created = 'created'
        running = 'running'
        finished = 'finished'

    class TaskTgtType(str, Enum):
        glob = 'glob'
        list = 'list'
        compound = 'compound'

    status: TaskStatus = Field(title='Status', default=TaskStatus.created)

    fun: str = Field(title='Salt fun')
    task_args: list[str] = Field(title='Args')
    task_kwargs: dict[str, Any] = Field(title='Kwargs')

    tgt_type: TaskTgtType = Field(title='Salt tgt type', default=TaskTgtType.glob)
    tgt: str = Field(title='Salt tgt', default='*')
    batch_size: int | None = Field(title='Batch size', default=None)


class TaskDBSchema(BaseDBSchema, TaskBaseSchema):
    pass


class TaskSchema(TaskDBSchema):
    pass


class TaskCreateSchema(TaskBaseSchema):
    pass


class TaskUpdateSchema(TaskBaseSchema):
    pass


class TaskListSchema(TaskDBSchema):
    pass


class TaskListQueryParams(PaginatedListQueryParams):
    model_config: ClassVar[ConfigDict] = {'extra': 'forbid'}
