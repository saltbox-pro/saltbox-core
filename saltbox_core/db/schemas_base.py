from typing import TypeVar

from pydantic import BaseModel, Field
from taskiq import TaskiqResult
from taskiq.depends.progress_tracker import TaskState

T = TypeVar('T')


class TaskiqTaskIdResponse(BaseModel):
    task_id: str = Field(title='Taskiq task ID')


class TaskiqTaskResult[T](TaskiqResult[T]):  # ty: ignore[invalid-base, invalid-argument-type]
    task_id: str = Field(title='Taskiq task ID')
    progress: TaskState | None = Field(title='Task progress')
    progress_meta: str | None = Field(title='Task progress meta')
