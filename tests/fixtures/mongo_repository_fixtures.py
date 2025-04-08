from pydantic import BaseModel

from salt_box_core.db.mongo.repository_base import BaseMongoRepository
from salt_box_core.db.mongo.schemas_base import IDMixin, TimezoneAwareDatetime


class ModelWithoutId(BaseModel):
    name: str
    description: str | None = None
    created: TimezoneAwareDatetime
    modified: TimezoneAwareDatetime


# Тестовая модель данных
class SampleModel(BaseModel, IDMixin):
    name: str
    description: str | None = None
    created: TimezoneAwareDatetime
    modified: TimezoneAwareDatetime


# Проекция модели для тестирования projection
class SampleModelProjection(BaseModel, IDMixin):
    name: str


# Модель для создания и обновления
class CreateUpdateModel(BaseModel):
    name: str
    description: str | None = None


# Тестовый репозиторий
class SampleRepository(BaseMongoRepository[SampleModel]):
    class Meta:
        collection_name = 'test_collection'
        auto_now_add_fields = ['created']
        auto_now_fields = ['modified']


# Тестовый репозиторий
class SampleRepositoryWithNoIdModel(BaseMongoRepository[ModelWithoutId]):
    class Meta:
        collection_name = 'test_collection'
        auto_now_add_fields = ['created']
        auto_now_fields = ['modified']


class SampleRepositoryWithoutCollectionName(BaseMongoRepository[SampleModel]):
    class Meta:
        auto_now_add_fields = ['created']
        auto_now_fields = ['modified']


class SampleRepositoryWithBadCreatedField(BaseMongoRepository[SampleModel]):
    class Meta:
        collection_name = 'test_collection'
        auto_now_add_fields = ['bad_created']


class SampleRepositoryWithBadModifiedField(BaseMongoRepository[SampleModel]):
    class Meta:
        collection_name = 'test_collection'
        auto_now_fields = ['bad_modified']
