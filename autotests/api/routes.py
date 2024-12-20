from enum import Enum


class Routes(str, Enum):
    JOBS = '/jobs'
    JOB_JID = '/jobs/{}'
    JOB_RETURN = '/jobs/{}/return'
    JOB_RETURNS_COUNT = '/jobs/{}/returns-count'
    FILTER_SCHEMA = '/filters/schema'
    FILTER_VALUES = '/filters/unique-grain-values'
    COLLECTION = '/collections'
    COLLECTION_ID = '/collections/{}'
    MINIONS = '/minions'
    MINIONS_ID = '/minions/{}'
    TASKS = '/tasks'
    TASKS_TEMPLATE = '/tasks/template'
    TASKS_TEMPLATE_ID = '/tasks/template/{}'
    TASKS_ID = '/tasks/{}'
    TASKS_RUN = '/tasks/{}/run'
    TASKS_STOP = '/tasks/{}/stop'

    def __str__(self) -> str:
        return self.value
