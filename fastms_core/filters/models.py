from __future__ import annotations

from typing import ClassVar

import pymongo
from beanie import Document

from fastms_core.filters.schemas import FilterSchema


class Filter(Document, FilterSchema):
    class Settings:
        name = 'filters'
        indexes: ClassVar[list] = [
            ('id', pymongo.TEXT),
        ]

    class Config:
        extra = 'allow'
