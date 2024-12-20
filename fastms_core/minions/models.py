from typing import ClassVar

import pymongo
from beanie import Document

from fastms_core.minions.schemas import MinionSchema


class Minion(Document, MinionSchema):
    class Settings:
        name = 'minions'
        indexes: ClassVar[list] = [
            ('minion_id', pymongo.TEXT),
        ]

    class Config:
        extra = 'allow'
