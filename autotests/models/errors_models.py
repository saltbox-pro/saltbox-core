from pydantic import BaseModel
from typing import List


class DetailItem(BaseModel):
    type: str
    loc: List[str]
    msg: str
    input: str


class ErrorResponse(BaseModel):
    detail: List[DetailItem]


class NotFoundModel(BaseModel):
    detail: str
