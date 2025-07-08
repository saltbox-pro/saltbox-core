from pydantic import BaseModel


class BurstJobsTestPostResponse(BaseModel):
    id: str


class BurstJobsTestDeleteResponse(BaseModel):
    deletions: int
