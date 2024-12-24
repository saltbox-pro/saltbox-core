from typing import Any

from pydantic import BaseModel


class TaskTemplateVariable(BaseModel):
    title: str
    name: str
    type: str
    required: bool
    choices: list[str | int | float] | None
    default_value: str | int | float | bool | None


class TaskTemplateBaseSchema(BaseModel):
    title: str
    fun: str
    variables: list[TaskTemplateVariable]
    task_args: list[str]
    task_kwargs: dict[str, Any]
