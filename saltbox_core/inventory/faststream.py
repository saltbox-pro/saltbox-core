from typing import Annotated

from faststream import Depends as FSDepends
from pymongo.asynchronous.database import AsyncDatabase
from redis.asyncio import Redis

from saltbox_core.inventory.repositories import InventoryRepository
from saltbox_core.inventory.services import InventoryService
from saltbox_core.jobs.repositories.job_repository import JobRepository
from saltbox_core.jobs.repositories.job_sc_repository import JobSchemaRepository
from saltbox_core.jobs.services.job_sc_service import JobSchemaService
from saltbox_core.jobs.services.job_services import JobService
from saltbox_core.masters.repositories.master_repository import MasterRepository
from saltbox_core.masters.services.master_service import MasterService
from saltbox_sdk.db.mongo.config import get_mongo
from saltbox_sdk.db.redis.config import get_redis_now


def fs_get_inventory_repository(
    db: Annotated[AsyncDatabase, FSDepends(get_mongo)]
) -> InventoryRepository:
    return InventoryRepository(db)


def fs_get_inventory_service(
    repo: Annotated[InventoryRepository,
    FSDepends(fs_get_inventory_repository)]
) -> InventoryService:
    return InventoryService(repo)


FSInventoryServiceDependency = Annotated[InventoryService, FSDepends(fs_get_inventory_service)]


def fs_get_job_repository(db: Annotated[Redis, FSDepends(get_redis_now)]) -> JobRepository:
    return JobRepository(db)


def fs_get_job_schema_repository(db: Annotated[AsyncDatabase, FSDepends(get_mongo)]) -> JobSchemaRepository:
    return JobSchemaRepository(db)


def fs_get_job_schema_service(
    repo: Annotated[JobSchemaRepository, FSDepends(fs_get_job_schema_repository)],
) -> JobSchemaService:
    return JobSchemaService(repo)


def fs_get_master_repository(db: Annotated[AsyncDatabase, FSDepends(get_mongo)]) -> MasterRepository:
    return MasterRepository(db)


def fs_get_master_service(repo: Annotated[MasterRepository, FSDepends(fs_get_master_repository)]) -> MasterService:
    return MasterService(repo)


def fs_get_job_service(
    rdb: Annotated[Redis, FSDepends(get_redis_now)],
    job_repository: Annotated[JobRepository, FSDepends(fs_get_job_repository)],
    job_schema_service: Annotated[JobSchemaService, FSDepends(fs_get_job_schema_service)],
    master_service: Annotated[MasterService, FSDepends(fs_get_master_service)],
) -> JobService:
    return JobService(
        rdb=rdb,
        job_repository=job_repository,
        job_schema_service=job_schema_service,
        master_service=master_service,
    )


FSJobServiceDependency = Annotated[JobService, FSDepends(fs_get_job_service)]
