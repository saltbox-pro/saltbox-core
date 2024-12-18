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

    def __str__(self) -> str:
        return self.value
