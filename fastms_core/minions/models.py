from __future__ import annotations

from typing import ClassVar

import pymongo
from beanie import Document

from fastms_core.minions.schemas import MinionCollectionSchema, MinionSchema


class Minion(Document, MinionSchema):
    class Settings:
        name = 'minions'
        indexes: ClassVar[list] = [
            ('minion_id', pymongo.TEXT),
        ]

    class Config:
        extra = 'allow'


class MinionCollection(Document, MinionCollectionSchema):
    class Settings:
        name = 'minion_collections'
        indexes: ClassVar[list] = [
            ('id', pymongo.TEXT),
        ]

    class Config:
        extra = 'allow'
