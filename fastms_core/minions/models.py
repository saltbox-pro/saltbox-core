from __future__ import annotations

from datetime import datetime
from typing import ClassVar

import pymongo
from beanie import Document
from pydantic import Field

from fastms_core.minions.schemas import GrainsSchema


def datetime_now_sec() -> datetime:
    return datetime.now().astimezone().replace(microsecond=0)


class Minion(Document):
    minion_id: str = Field(title='Minion ID')
    master: str = Field(title='Master')
    grains: GrainsSchema | None = None
    created: datetime = Field(default_factory=datetime_now_sec)
    modified: datetime = Field(default_factory=datetime_now_sec)

    class Settings:
        name = 'minions'
        indexes: ClassVar[list] = [
            ('minion_id', pymongo.TEXT),
        ]
        # use_cache = True

    class Config:
        extra = 'allow'
