import logging.config
import re
from enum import Enum
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict, Field, model_validator

from salt_box_core.config import LOG_CONFIG
from salt_box_core.db.mongo.schemas_base import CreatedModifiedMixin, IDMixin, PaginatedListParams

logging.config.dictConfig(LOG_CONFIG.model_dump())

logger = logging.getLogger(__name__)


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


class TaskTemplateReadOnlyFieldsMixin:
    # slug: str = Field(title='Slug', pattern=r'^[a-z0-9-]+$', min_length=3, max_length=30)

    fun: str = Field(title='Salt fun', examples=['salt.ping'])

    variables: list[TaskTemplateVariable] = Field(title='Variables')
    task_args: list[str] = Field(title='Args', examples=[['const_arg', '<<task_var.var_name>>']])
    task_kwargs: dict[str, Any] = Field(
        title='Kwargs', examples=[{'const_kwarg': 'const_kwarg_value', 'var_kwarg': '<<task_var.var_name>>'}]
    )


class TaskTemplateEditableFieldsMixin:
    title: str = Field(title='Title')


class TaskTemplateCreateSchema(BaseModel, TaskTemplateEditableFieldsMixin, TaskTemplateReadOnlyFieldsMixin):
    @model_validator(mode='after')
    def validate_variables(self) -> 'TaskTemplateCreateSchema':
        str_values_of_args_and_kwargs: list[str] = [
            val for val in self.task_args + list(self.task_kwargs.values()) if isinstance(val, str)
        ]
        var_names: list[str] = [var.name for var in self.variables]

        # Check for unused variables
        for var_name in var_names:
            var_str = f'<<task_var.{var_name}>>'
            var_found: bool = False

            for arg in str_values_of_args_and_kwargs:
                if var_str in arg:
                    var_found = True
                    break

            if var_found is False:
                msg: str = f'The variable "{var_name}" is defined, but not used'
                raise ValueError(msg)

        # Check for unknown variables
        var_pattern = r'<<task_var\.(.+)>>'
        for var in str_values_of_args_and_kwargs:
            for match in re.finditer(var_pattern, var):
                if match.group(1) not in var_names:
                    msg = f'The variable "{match.group(1)}" is not defined'
                    raise ValueError(msg)

        return self


class TaskTemplateUpdateSchema(BaseModel, TaskTemplateEditableFieldsMixin):
    model_config = ConfigDict(
        extra='forbid',
    )


class TaskTemplateModel(
    BaseModel, CreatedModifiedMixin, TaskTemplateEditableFieldsMixin, TaskTemplateReadOnlyFieldsMixin, IDMixin
):
    pass


class TaskTemplateListQueryParams(PaginatedListParams):
    model_config: ClassVar[ConfigDict] = {'extra': 'forbid'}
