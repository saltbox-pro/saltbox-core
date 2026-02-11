from saltbox_core.jobs.repositories.job_repository import JobRepository
from saltbox_core.jobs.repositories.job_return_repository import JobReturnRepository
from saltbox_core.jobs.repositories.job_sc_repository import JobSchemaRepository
from saltbox_core.masters.repositories.master_repository import MasterRepository
from saltbox_core.minion_collections.repositories.collection_repository import CollectionRepository
from saltbox_core.minion_collections.repositories.minion_repository import MinionRepository
from saltbox_core.pillars_v2.repository import PillarRepository
from saltbox_core.settings.repository import SettingsSlsRepoRepository
from saltbox_core.tasks.repositories.tasks_minion import TaskMinionRepository
from saltbox_core.tasks.repositories.tasks_template import TaskTemplateRepository
from saltbox_sdk.db.mongo.config import get_mongo_db
from saltbox_sdk.db.mongo.repository_base import BaseMongoRepository
from saltbox_sdk.db.redis.config import get_redis_now


async def init_mongo_db() -> None:
    """Initialize MongoDB collections"""

    database = get_mongo_db()
    rdb = get_redis_now()

    reps: list[BaseMongoRepository] = [
        JobRepository(database),
        JobReturnRepository(database, rdb),
        JobSchemaRepository(database),
        MasterRepository(database),
        MinionRepository(database),
        CollectionRepository(database),
        SettingsSlsRepoRepository(database),
        TaskMinionRepository(database),
        TaskTemplateRepository(database),
        PillarRepository(database),
    ]
    for repo in reps:
        await repo.create_collection()
