from typing import Annotated

from faststream import Depends as FSDepends

from saltbox_core.jobs.repositories.job_repository import JobRepository
from saltbox_core.jobs.repositories.job_sc_repository import JobSchemaRepository
from saltbox_core.jobs.services.job_sc_service import JobSchemaService
from saltbox_core.jobs.services.job_services import JobService
from saltbox_core.masters.faststream import FSMasterServiceDependency
from saltbox_sdk.faststream_utils.dependencies import FSMongoDependency, FSRedisDependency


def fs_get_job_repository(db: FSRedisDependency) -> JobRepository:
    return JobRepository(db)


FSJobRepositoryDependency = Annotated[JobRepository, FSDepends(fs_get_job_repository)]


def fs_get_job_schema_repository(db: FSMongoDependency) -> JobSchemaRepository:
    return JobSchemaRepository(db)


FSJobSchemaRepositoryDependency = Annotated[JobSchemaRepository, FSDepends(fs_get_job_schema_repository)]


def fs_get_job_schema_service(repo: FSJobSchemaRepositoryDependency) -> JobSchemaService:
    return JobSchemaService(repo)


FSJobSchemaServiceDependency = Annotated[JobSchemaService, FSDepends(fs_get_job_schema_service)]


def fs_get_job_service(
    rdb: FSRedisDependency,
    job_repository: FSJobRepositoryDependency,
    job_schema_service: FSJobSchemaServiceDependency,
    master_service: FSMasterServiceDependency,
) -> JobService:
    return JobService(
        rdb=rdb,
        job_repository=job_repository,
        job_schema_service=job_schema_service,
        master_service=master_service,
    )


FSJobServiceDependency = Annotated[JobService, FSDepends(fs_get_job_service)]
