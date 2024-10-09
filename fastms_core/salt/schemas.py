from __future__ import annotations

from pydantic import BaseModel, Field


class AuthItem(BaseModel):
    eauth: str
    expire: float
    perms: list[str]
    start: float
    token: str
    user: str


class AuthResponse(BaseModel):
    return_: list[AuthItem] = Field(alias='return', min_length=1)
