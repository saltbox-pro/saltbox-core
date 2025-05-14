from pydantic import BaseModel, Field

from salt_box_core.event_bus.master_bus_base_messages import BusMasterMessage


class MasterMessageSlsRepoModel(BaseModel):
    local_path: str
    name: str
    branch: str
    root: str = Field(description='Path in repository to set as Salt GitFS root')


class ListSlsReposMessage(BusMasterMessage):
    repos: list[MasterMessageSlsRepoModel]
