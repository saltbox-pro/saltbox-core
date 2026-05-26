from typing import ClassVar

from saltbox_core.tkq import broker, queue_notify
from saltbox_sdk.db.mongo.schemas_base import PyObjectId
from saltbox_sdk.serivces.mongo_base_with_notify_service import MongoBaseWithNotifyService


class _NotifyServicesStoreSingleton:
    instance: ClassVar['_NotifyServicesStoreSingleton | None'] = None
    services: dict[str, MongoBaseWithNotifyService]

    def __new__(cls) -> '_NotifyServicesStoreSingleton':
        if cls.instance is None:
            cls.instance = super().__new__(cls)
            cls.instance.services = cls.__get_services()

        return cls.instance

    @classmethod
    def __get_services(cls) -> dict[str, MongoBaseWithNotifyService]:
        from saltbox_core.jobs.repositories.job_repository import JobRepository
        from saltbox_core.jobs.repositories.job_return_repository import JobReturnRepository
        from saltbox_core.jobs.repositories.job_sc_repository import JobSchemaRepository
        from saltbox_core.jobs.services.job_return_service import JobReturnService
        from saltbox_core.jobs.services.job_sc_service import JobSchemaService
        from saltbox_core.jobs.services.job_services import JobService
        from saltbox_core.masters.repositories.master_repository import MasterRepository
        from saltbox_core.masters.services.master_service import MasterService
        from saltbox_core.minion_collections.repositories.collection import CollectionRepository
        from saltbox_core.minion_collections.repositories.minion import MinionRepository
        from saltbox_core.minion_collections.services.collection import CollectionService
        from saltbox_core.minion_collections.services.minion import MinionService
        from saltbox_core.tasks.repositories.task import TaskRepository
        from saltbox_core.tasks.repositories.tasks_minion import TaskMinionRepository
        from saltbox_core.tasks.repositories.tasks_status import TaskStatusRepository
        from saltbox_core.tasks.repositories.tasks_template import TaskTemplateRepository
        from saltbox_core.tasks.services.task import TaskService
        from saltbox_core.tasks.services.tasks_minion import TaskMinionService
        from saltbox_core.tasks.services.tasks_status import TaskStatusService
        from saltbox_core.tasks.services.tasks_template import TaskTemplateService
        from saltbox_sdk.db.mongo.config import get_mongo_db
        from saltbox_sdk.db.redis.config import get_redis_now

        rdb = get_redis_now()
        mongo_db = get_mongo_db()

        master_repository = MasterRepository(database=mongo_db)
        master_service = MasterService(repo=master_repository)
        job_schema_repository = JobSchemaRepository(database=mongo_db)
        job_schema_service = JobSchemaService(repo=job_schema_repository)
        job_return_repository = JobReturnRepository(database=mongo_db, rdb=rdb)
        job_return_service = JobReturnService(repo=job_return_repository, rdb=rdb)
        job_repository = JobRepository(database=mongo_db)
        job_service = JobService(
            rdb=rdb,
            job_repository=job_repository,
            job_schema_service=job_schema_service,
            job_return_service=job_return_service,
            master_service=master_service,
        )

        collection_repository = CollectionRepository(database=mongo_db)
        collection_service = CollectionService(repo=collection_repository)
        minion_repository = MinionRepository(database=mongo_db)
        minion_service = MinionService(repo=minion_repository)

        task_status_repository = TaskStatusRepository(database=mongo_db)
        task_status_service = TaskStatusService(repo=task_status_repository)
        task_template_repository = TaskTemplateRepository(database=mongo_db)
        task_template_service = TaskTemplateService(repo=task_template_repository)
        task_minion_repository = TaskMinionRepository(database=mongo_db)
        task_minion_service = TaskMinionService(repo=task_minion_repository, rdb=rdb)
        task_repository = TaskRepository(database=mongo_db)
        task_service = TaskService(
            repo=task_repository,
            rdb=rdb,
            task_status_service=task_status_service,
            task_template_service=task_template_service,
            task_minion_service=task_minion_service,
            job_schema_service=job_schema_service,
            collections_service=collection_service,
            minion_service=minion_service,
        )

        return {
            'job_return_service': job_return_service,
            'job_service': job_service,
            'task_service': task_service,
            'task_minion_service': task_minion_service,
        }


@broker.task(
    queue_name=queue_notify.name,
    unique_kwargs=['service_name', 'document_id', 'action'],
    unique_lock_timeout=120,
)
async def send_notify_by_mongo_service(
    service_name: str,
    document_id: str,
    action: str,
) -> None:
    did = PyObjectId(document_id)

    service = _NotifyServicesStoreSingleton().services.get(service_name)

    if service is None:
        msg = f'Service {service_name} not found'
        raise RuntimeError(msg)

    await service.run_notify(obj_id=did, action=action)
