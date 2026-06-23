from saltbox_core.jobs.repositories.job_repository import JobRepository
from saltbox_core.jobs.repositories.job_return_repository import JobReturnRepository
from saltbox_core.jobs.repositories.job_sc_repository import JobSchemaRepository
from saltbox_core.masters.repositories.master_repository import MasterRepository
from saltbox_core.minion_collections.repositories.collection import CollectionRepository
from saltbox_core.minion_collections.repositories.extra_data import ExtraDataRepository
from saltbox_core.minion_collections.repositories.extra_data_category import ExtraDataCategoryRepository
from saltbox_core.minion_collections.repositories.minion import MinionRepository
from saltbox_core.pillars.repository import PillarRepository
from saltbox_core.task_templates.repositories.source import TemplateSourceRepository
from saltbox_core.tasks.repositories.task import TaskRepository
from saltbox_core.tasks.repositories.tasks_minion import TaskMinionRepository
from saltbox_core.tasks.repositories.tasks_status import TaskStatusRepository
from saltbox_sdk.db.mongo.config import get_mongo_db
from saltbox_sdk.db.mongo.repository_base import BaseMongoRepository
from saltbox_sdk.db.redis.config import get_redis_now


async def init_mongo_db() -> None:
    """Initialize MongoDB collections"""

    database = get_mongo_db()
    rdb = get_redis_now()

    extra_data_category_repository = ExtraDataCategoryRepository(database)
    extra_data_repository = ExtraDataRepository(database, extra_data_category_repository)

    reps: list[BaseMongoRepository] = [
        JobRepository(database),
        JobReturnRepository(database, rdb),
        JobSchemaRepository(database),
        MasterRepository(database),
        extra_data_category_repository,
        extra_data_repository,
        MinionRepository(database, extra_data_repository),
        CollectionRepository(database),
        TaskRepository(database),
        TaskMinionRepository(database),
        TaskStatusRepository(database),
        PillarRepository(database),
        TemplateSourceRepository(database),
    ]
    for repo in reps:
        await repo.create_collection()
