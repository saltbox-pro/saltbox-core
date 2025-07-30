from pydantic import BaseModel, Field
from taskiq import TaskiqResult
from taskiq.depends.progress_tracker import TaskState


class TaskiqTaskIdResponse(BaseModel):
    task_id: str = Field(title='Taskiq task ID')


class TaskiqTaskResult(TaskiqResult):
    task_id: str = Field(title='Taskiq task ID')
    progress: TaskState | None = Field(title='Task progress')
    progress_meta: str | None = Field(title='Task progress meta')
