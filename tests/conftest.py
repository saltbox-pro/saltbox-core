import mongomock
import pytest


class AsyncMockCollection:
    """Asynchronous wrapper for mongomock collection"""

    def __init__(self, collection, mocker):
        self.collection = collection
        self._inserted_docs = {}  # for storing inserted documents
        self.mocker = mocker

    async def insert_one(self, document, session=None):
        # Check if the document already exists in the collection
        if 'slug' in document and any(doc.get('slug') == document['slug'] for doc in self._inserted_docs.values()):
            from pymongo.errors import DuplicateKeyError as MongoDuplicateKeyError

            raise MongoDuplicateKeyError('Duplicate slug')

        result = self.collection.insert_one(document)
        # Save the inserted document in the mock
        self._inserted_docs[result.inserted_id] = document
        return self.mocker.MagicMock(inserted_id=result.inserted_id)

    def find(self, filter=None, projection=None, limit=0, skip=0, sort=None, session=None):
        """Эмуляция метода find"""
        cursor_results = []

        if filter and '_id' in filter:
            # If the filter contains an _id, we check if it exists in the inserted documents
            doc_id = filter['_id']
            if doc_id in self._inserted_docs:
                cursor_results = [{'_id': doc_id, **self._inserted_docs[doc_id]}]
        else:
            # Else find with mongomock
            cursor_results = list(self.collection.find(filter=filter, projection=projection))
            if skip > 0:
                cursor_results = cursor_results[skip:]
            if limit > 0:
                cursor_results = cursor_results[:limit]
            if sort:
                for field, direction in reversed(sort):
                    cursor_results.sort(key=lambda x: x.get(field), reverse=(direction == -1))

        mock_cursor = self.mocker.MagicMock()
        mock_cursor.to_list = self.mocker.AsyncMock(return_value=cursor_results)
        return mock_cursor

    async def count_documents(self, filter, limit=0, session=None):
        return self.collection.count_documents(filter)

    async def update_one(self, filter, update, upsert=False, session=None):
        """Эмуляция метода update_one"""
        # Проверяем, если в фильтре есть _id
        if '_id' in filter:
            doc_id = filter['_id']
            if doc_id in self._inserted_docs:
                # Обновляем документ в нашем внутреннем хранилище
                if '$set' in update:
                    for key, value in update['$set'].items():
                        self._inserted_docs[doc_id][key] = value

                # Обновляем документ в mongomock
                result = self.collection.update_one(filter, update, upsert=upsert)
                return self.mocker.MagicMock(modified_count=result.modified_count)

        # Если не нашли документ по _id, пробуем обновить через mongomock
        result = self.collection.update_one(filter, update, upsert=upsert)
        return self.mocker.MagicMock(modified_count=result.modified_count)

    # TODO @: check and fix this
    async def find_one_and_update(
        self, filter, update, upsert=False, return_document=None, session=None, projection=None
    ):
        """Эмуляция метода find_one_and_update"""
        # Проверяем, если в фильтре есть _id
        if '_id' in filter:
            doc_id = filter['_id']
            if doc_id in self._inserted_docs:
                # Обновляем документ в нашем внутреннем хранилище
                if '$set' in update:
                    for key, value in update['$set'].items():
                        self._inserted_docs[doc_id][key] = value

                # Обновляем документ в mongomock
                result = self.collection.find_one_and_update(
                    filter, update, upsert=upsert, return_document=return_document, projection=projection
                )
                return result
                # return self.mocker.MagicMock(modified_count=result)

        # Если не нашли документ по _id, пробуем обновить через mongomock
        result = self.collection.find_one_and_update(
            filter, update, upsert=upsert, return_document=return_document, projection=projection
        )
        return result
        # return self.mocker.MagicMock(modified_count=result)

    async def delete_one(self, filter, session=None):
        """Эмуляция метода delete_one"""
        # Если в фильтре есть _id
        if '_id' in filter:
            doc_id = filter['_id']
            if doc_id in self._inserted_docs:
                # Удаляем документ из нашего внутреннего хранилища
                del self._inserted_docs[doc_id]
                # Удаляем документ из mongomock
                result = self.collection.delete_one(filter)
                return self.mocker.MagicMock(deleted_count=result.deleted_count)

        # Если не нашли документ по _id, пробуем удалить через mongomock
        result = self.collection.delete_one(filter)
        return self.mocker.MagicMock(deleted_count=result.deleted_count)

    async def delete_many(self, filter, session=None):
        """Эмуляция метода delete_many"""
        # Удаляем документы из нашего внутреннего хранилища, если они соответствуют фильтру
        to_delete = []
        for doc_id, doc in list(self._inserted_docs.items()):
            matches = True
            for key, value in filter.items():
                if key not in doc or doc[key] != value:
                    matches = False
                    break
            if matches:
                to_delete.append(doc_id)

        for doc_id in to_delete:
            del self._inserted_docs[doc_id]

        # Удаляем документы из mongomock
        result = self.collection.delete_many(filter)
        return self.mocker.MagicMock(deleted_count=result.deleted_count)


class AsyncMockDatabase:
    """Asynchronous wrapper for mongomock database"""

    def __init__(self, mocker):
        self.client = mongomock.MongoClient()
        self.db = self.client.test_db
        self.collections = {}
        self.mocker = mocker

    def __getitem__(self, collection_name):
        if collection_name not in self.collections:
            self.collections[collection_name] = AsyncMockCollection(self.db[collection_name], self.mocker)
        return self.collections[collection_name]


@pytest.fixture
def mocked_db(mocker):
    """Fixture for mocking MongoDB database using mongomock.
    This fixture creates an instance of AsyncMockDatabase and
    returns it for use in tests.
    """
    return AsyncMockDatabase(mocker)
