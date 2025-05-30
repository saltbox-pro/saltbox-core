from enum import Enum, auto
from typing import Any, Generic, overload

from pydantic import BaseModel

from salt_box_core.db.exceptions import MultipleObjectsFoundError, ObjectDeleteError, ObjectNotFoundError
from salt_box_core.db.mongo.repository_base import BaseMongoRepository, ModelType, ProjectionModel, T
from salt_box_core.db.mongo.schemas_base import BaseTreeModel, PyObjectId


class OnDelete(Enum):
    cascade = auto()
    protected = auto()


class BaseTreeMongoRepository(BaseMongoRepository[T], Generic[T]):
    class Meta(BaseMongoRepository.Meta):
        on_delete = OnDelete.protected

    @overload
    async def get_children(self, target: PyObjectId | ModelType) -> list[T]: ...

    @overload
    async def get_children(
        self, target: PyObjectId | ModelType, projection_model: type[ProjectionModel]
    ) -> list[ProjectionModel]: ...

    async def get_children(
        self, target: PyObjectId | ModelType, projection_model: type[ProjectionModel] | None = None
    ) -> list[T] | list[ProjectionModel]:
        if isinstance(target, BaseModel):
            if hasattr(target, 'id'):
                target_id = target.id
            else:
                msg = 'Target must be have "id" field"'
                raise TypeError(msg)
        elif isinstance(target, PyObjectId):
            target_id = target
        else:
            msg = 'Unknown target type'  # type: ignore
            raise TypeError(msg)

        if projection_model is not None:
            return await self.get_list({'parent_id': target_id}, projection_model=projection_model, limit=0, skip=0)
        else:
            return await self.get_list({'parent_id': target_id}, limit=0, skip=0)

    async def get_parent_id(self, target: PyObjectId | ModelType) -> PyObjectId | None:
        if isinstance(target, BaseModel):
            if hasattr(target, 'parent_id'):
                if isinstance(target.parent_id, PyObjectId):
                    return target.parent_id

                msg = 'Type of "parent_id" must be "PyObjectId"'
                raise ValueError(msg)

            if hasattr(target, 'id'):
                return await self.get_parent_id(PyObjectId(target.id))

            msg = 'Target must be have "id" field'
            raise ValueError(msg)

        elif isinstance(target, PyObjectId):
            query = {'_id': target}
            obj_data = await self.collection.find(filter=query, projection={'_id': 1, 'parent_id': 1}).to_list()

            if len(obj_data) == 0:
                raise ObjectNotFoundError(obj_type=self.Meta.collection_name, query=query)
            elif len(obj_data) > 1:
                raise MultipleObjectsFoundError

            return PyObjectId(obj_data[0]['parent_id']) if 'parent_id' in obj_data[0] else None
        else:
            msg = 'Unknown target type'  # type: ignore
            raise TypeError(msg)

    @overload
    async def get_parent(self, target: PyObjectId | ModelType) -> T | None: ...

    @overload
    async def get_parent(
        self, target: PyObjectId | ModelType, projection_model: type[ProjectionModel]
    ) -> ProjectionModel | None: ...

    async def get_parent(
        self, target: PyObjectId | ModelType, projection_model: type[ProjectionModel] | None = None
    ) -> T | ProjectionModel | None:
        parent_id = await self.get_parent_id(target)

        if parent_id is None:
            return None

        try:
            if projection_model is not None:
                return await self.get(parent_id, projection_model=projection_model)
            else:
                return await self.get(parent_id)
        except ObjectNotFoundError:
            return None

    async def delete(self, query: PyObjectId | dict[str, Any]) -> int:
        query = self.__prepare_query__(query)
        projection = self._get_projection_from_model(BaseTreeModel)
        deleted_count = 0

        find_result = await self.collection.find(filter=query, projection=projection).to_list()

        if len(find_result) == 0:
            raise ObjectNotFoundError(obj_type=self.Meta.collection_name, query=query)
        elif len(find_result) > 1:
            raise MultipleObjectsFoundError

        obj = BaseTreeModel.model_validate(find_result[0])

        if self.Meta.on_delete == OnDelete.protected:
            if self.exists({'parent_id': obj.id}):
                raise ObjectDeleteError(detail='The object cannot be deleted because it has child elements')
        elif self.Meta.on_delete == OnDelete.cascade:
            for child in await self.get_children(obj, projection_model=BaseTreeModel):
                deleted_count += await self.delete(child.id)

        result = await self.collection.delete_one(query)
        deleted_count += result.deleted_count
        return deleted_count
