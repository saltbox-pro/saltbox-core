from datetime import datetime, timedelta

from pydantic import BaseModel, Field, computed_field

from saltbox_bridge_messages import Iso8601ZDatetime


class BurstJobsTestPostResponse(BaseModel):
    id: str


class BurstJobsTestDeleteResponse(BaseModel):
    deletions: int


class BurstJobsTestStatsResponse(BaseModel):
    jobs_created: int = Field(
        description=(
            'Total amount of jobs, created while bursting.'
            '`1 - jobs_created / requested duration * requested rate` is loss metric.'
        )
    )
    first_job_time: Iso8601ZDatetime | None = Field(
        description=(
            'Fist message timestamp may be useful to estimate time lag before request and bursting.'
        )
    )
    last_job_time: Iso8601ZDatetime | None = Field()

    @computed_field(
        description=(
            'Seconds between last and first fake job in burst timestamps.'
            '`requested duration / receiving_duration` is a metric for time lag.'
        )
    )
    def receiving_duration(self) -> float:
        if self.last_job_time is not None and self.first_job_time is not None:
            return (self.last_job_time - self.first_job_time).total_seconds()
        else:
            return 0
