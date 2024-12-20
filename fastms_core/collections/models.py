from typing import ClassVar

import pymongo
from beanie import Document

from fastms_core.collections.schemas import MinionCollectionSchema


class MinionCollection(Document, MinionCollectionSchema):
    class Settings:
        name = 'minion_collections'
        indexes: ClassVar[list] = [
            ('id', pymongo.TEXT),
        ]

    class Config:
        extra = 'allow'
