from enum import StrEnum

from pydantic import BaseModel


class PillarSelector(BaseModel):
    master_id: str
    minion_id: str | None = None
    name: str


class PillarModel(BaseModel):
    master_id: str
    minion_id: str | None = None

    name: str
    value: str


class PillarCSVParseResultErrorCode(StrEnum):
    minion_does_not_exist = 'minion_does_not_exist'
    master_does_not_exist = 'master_does_not_exist'
    pillar_already_exists = 'pillar_already_exists'


class PillarCSVParseResult(PillarModel):
    error_codes: list[PillarCSVParseResultErrorCode] = []


class PillarImportSchema(BaseModel):
    items: list[PillarModel]
    update_existing: bool = False


class PillarImportResultItemStatus(StrEnum):
    success = 'success'
    fail = 'fail'
    skipped = 'skipped'


class PillarImportResultItemSchema(PillarModel):
    status: PillarImportResultItemStatus = PillarImportResultItemStatus.success
    error_text: str | None = None


class PillarImportResultSchema(BaseModel):
    items: list[PillarImportResultItemSchema] = []
    skipped: int = 0
    succeed: int = 0
    failed: int = 0


class PillarListQueryParams(BaseModel):
    master_id: str
    minion_id: str | None = None
    only_for_minion: bool = False


class PillarsActions(StrEnum):
    LIST = 'list'
    CREATE = 'create'
    UPDATE = 'update'
    DELETE = 'delete'
    EXPORT = 'export'
    VALIDATE = 'validate'
    IMPORT = 'import'
