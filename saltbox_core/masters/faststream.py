from typing import Annotated

from faststream import Depends as FSDepends

from saltbox_core.masters.repositories.master_repository import MasterRepository
from saltbox_core.masters.services.master_service import MasterService
from saltbox_sdk.faststream_utils.dependencies import FSMongoDependency


def fs_get_master_repository(db: FSMongoDependency) -> MasterRepository:
    return MasterRepository(db)


FSMasterRepositoryDependency = Annotated[MasterRepository, FSDepends(fs_get_master_repository)]


def fs_get_master_service(repo: FSMasterRepositoryDependency) -> MasterService:
    return MasterService(repo)


FSMasterServiceDependency = Annotated[MasterService, FSDepends(fs_get_master_service)]
