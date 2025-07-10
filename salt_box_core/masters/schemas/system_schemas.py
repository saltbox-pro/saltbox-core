from pydantic import BaseModel, Field, computed_field

from saltbox_bridge_messages import Iso8601ZDatetime


class BurstJobsTestPostResponse(BaseModel):
    id: str


class BurstJobsTestDeleteResponse(BaseModel):
    deletions: int


class BurstJobsTestStatsResponse(BaseModel):
    messages_sent: int = Field(description='Amount of messages fired by burster')
    messages_overdue: int = Field(description='Amount of messages which were sent later than expected')
    burst_start: Iso8601ZDatetime = Field(description='Timestamp of the burst beginning')
    burst_end: Iso8601ZDatetime = Field(description='Timestamp of the burst end')
    jobs_created: int = Field(
        description=(
            'Total amount of jobs created while bursting.'
            ' `1 - jobs_created / messages_sent` is a Bridge loss metric.'
            ' `1 - jobs_created / requested duration * requested rate` is a Bridge loss metric'
            ' including dropped by burster.'
        )
    )
    first_job_time: Iso8601ZDatetime | None = Field(
        description=(
            'Fist message timestamp may be useful to estimate time lag between request and bursting.'
        )
    )
    last_job_time: Iso8601ZDatetime | None = Field()

    @computed_field(description='First-last job timestamps delta. Usefult to estimate loss tail.')
    def receiving_seconds(self) -> float:
        if self.last_job_time is not None and self.first_job_time is not None:
            return (self.last_job_time - self.first_job_time).total_seconds()
        else:
            return 0

    @computed_field(description='Duration of bursting')
    def bursting_seconds(self) -> float:
        return (self.burst_end - self.burst_start).total_seconds()
