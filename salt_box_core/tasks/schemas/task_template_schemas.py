from enum import Enum
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict, Field, model_validator

# from salt_box_core.config import logger
from salt_box_core.db.mongo.schemas_base import CreatedModifiedMixin, IDMixin, PaginatedListParams, PyObjectId


class TaskTemplateVariable(BaseModel):
    class TaskTemplateType(str, Enum):
        string = 'str'
        number = 'number'
        bool = 'bool'
        choices = 'choices'

    title: str = Field(title='Title')
    name: str = Field(title='Name', pattern=r'^[a-zA-Z0-9-_]+$')
    type: TaskTemplateType = Field(title='Type', default=TaskTemplateType.string)
    required: bool = Field(title='Required', default=True)
    choices: list[str | int | float] | None = Field(title='Choices', default=None)
    default_value: str | int | float | bool | None = Field(title='Default value', default=None)

    @model_validator(mode='after')
    def validate_default_value_and_choices(self) -> 'TaskTemplateVariable':
        if self.type == self.TaskTemplateType.string and not isinstance(self.default_value, str | None):
            msg: str = '"default_value" must by string for task template type "string"'
            raise ValueError(msg)
        elif self.type == self.TaskTemplateType.number and not isinstance(self.default_value, int | float | None):
            msg = '"default_value" must by integer or float for task template type "number"'
            raise ValueError(msg)
        elif self.type == self.TaskTemplateType.bool and not isinstance(self.default_value, bool | None):
            msg = '"default_value" must by boolean for task template type "bool"'
            raise ValueError(msg)
        elif self.type == self.TaskTemplateType.choices and not self.choices:
            msg = '"choices" must have at least one value for task template type "choices"'
            raise ValueError(msg)

        return self

    def validate_value(self, value: str | int | float) -> str | int | float:
        value_type = type(value)

        if self.type == self.TaskTemplateType.string and value_type is not str:
            msg = f'Variable "{self.name}" must be a string'
            raise ValueError(msg)
        elif self.type == TaskTemplateVariable.TaskTemplateType.number and value_type not in [int, float]:
            msg = f'Variable "{self.name}" must be an integer or float'
            raise ValueError(msg)
        elif self.type == TaskTemplateVariable.TaskTemplateType.bool and value_type is not bool:
            msg = f'Variable "{self.name}" must be a boolean'
            raise ValueError(msg)
        elif self.type == TaskTemplateVariable.TaskTemplateType.choices and self.choices and value not in self.choices:
            msg = f'Variable "{self.name}" must be one of {self.choices}'
            raise ValueError(msg)

        return value


class ReadOnlyFieldsShortMixin:
    fun: str = Field(title='Salt fun', examples=['salt.ping'])

    variables: list[TaskTemplateVariable] = Field(title='Variables')
    task_args: list[str] = Field(title='Args', examples=[['const_arg', '<<task_var.var_name>>']])
    task_kwargs: dict[str, Any] = Field(
        title='Kwargs', examples=[{'const_kwarg': 'const_kwarg_value', 'var_kwarg': '<<task_var.var_name>>'}]
    )

    title: str = Field(title='Template title')
    name: str = Field(title='sls name')
    repo_id: PyObjectId = Field(title='Repository ID')
    commit_hash: str = Field(title='Commit hash')


class ReadOnlyFieldsFullMixin(ReadOnlyFieldsShortMixin):
    json_schema: dict = Field(title='JSON schema')
    ui_schema: dict = Field(title='UI schema', default_factory=dict)


class EditableFieldsShortMixin: ...


class EditableFieldsFullMixin(EditableFieldsShortMixin): ...


class TaskTemplateCreateSchema(BaseModel, EditableFieldsFullMixin, ReadOnlyFieldsFullMixin):
    pass


class TaskTemplateUpdateSchema(BaseModel, EditableFieldsFullMixin, ReadOnlyFieldsFullMixin):
    model_config = ConfigDict(
        extra='forbid',
    )


class TaskTemplateShortSchema(BaseModel, ReadOnlyFieldsShortMixin, EditableFieldsShortMixin, IDMixin):
    pass


class TaskTemplateModel(BaseModel, CreatedModifiedMixin, EditableFieldsFullMixin, ReadOnlyFieldsFullMixin, IDMixin):
    pass


class TaskTemplateListQueryParams(PaginatedListParams):
    model_config: ClassVar[ConfigDict] = {'extra': 'forbid'}
