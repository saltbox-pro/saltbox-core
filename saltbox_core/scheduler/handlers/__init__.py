from saltbox_core.scheduler.handlers.run_job import run_job
from saltbox_core.scheduler.handlers.run_task import run_task

scheduler_handlers = {
    'run_task': run_task,
    'run_job': run_job,
}
