from enum import Enum


class Routes(str, Enum):
    JOBS = '/jobs'
    JOB_JID = '/jobs/{}'
    JOB_RETURN = '/jobs/{}/return'
    JOB_RETURNS_COUNT = '/jobs/{}/returns-count'
    MINIONS = '/minions'
    MINIONS_FILTER_SCHEMA = '/minions/filter-schema'
    MINIONS_ID = '/minions/{}'

    def __str__(self) -> str:
        return self.value
