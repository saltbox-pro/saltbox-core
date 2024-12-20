from typing import Optional, List, Dict, Any
from pydantic import BaseModel


class DetailItem(BaseModel):
    type: str
    loc: List[str]
    msg: str
    input: Any
    ctx: Optional[Dict[str, Any]] = None  # The 'ctx` field may not be required


class ErrorResponse(BaseModel):
    detail: List[DetailItem]


class ErrorTextModel(BaseModel):
    detail: str
