from pydantic import BaseModel

from salt_box_core.event_bus.masters_bus import BusMasterMessage


class MasterMessageSlsRepoModel(BaseModel):
    local_path: str
    name: str
    branch: str


class ListSlsReposMessage(BusMasterMessage):
    repos: list[MasterMessageSlsRepoModel]
