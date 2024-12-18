from pydantic import BaseModel


class FilterSchemaModel(BaseModel):
    name: str
    label: str
