from enum import Enum


class Routes(str, Enum):
    JOBS = '/jobs'
    JOB_JID = '/jobs/{}'
    JOB_RETURN = '/jobs/{}/return'
    JOB_RETURNS_COUNT = '/jobs/{}/returns-count'
    MINIONS_FILTER_SCHEMA = '/minions/filter-schema'
    MINIONS_FILTER_VALUES = '/minions/filter-values'
    MINIONS_COLLECTION = '/minions/collection'
    MINIONS_COLLECTION_ID = '/minions/collection/{}'
    MINIONS = '/minions'
    MINIONS_ID = '/minions/{}'

    def __str__(self) -> str:
        return self.value
