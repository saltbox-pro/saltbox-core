from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from saltbox_core.jobs.schemas.job_schemas import StrJid
from saltbox_core.utilities.salt import fill_salt_kwarg_from_arg
from saltbox_sdk.db.mongo.schemas_base import IDMixin
from saltbox_sdk.db.schemas_base import CreatedModifiedMixin, Source

# Job returns


class JobReturnReadOnlyFieldsMixin:
    minion_id: str
    salt_master: str
    retcode: int
    jid: StrJid
    fun: str
    fun_args: list | None = None
    fun_kwarg: dict | None = None
    user: str | None = None
    stamp: str
    source: Source | None = None


class JobReturnEditableFieldsMixin: ...


class JobReturnComputedFieldsMixin:
    @property
    def success(self) -> bool:
        """
        Does job finished successfully

        Field exists in an Event Bus object, but not for all cases. E.g. field is
        missing on `salt.call` return. For convenience in the model it is True when
        retcode is zero and vice versa.
        """
        return not self.retcode  # type: ignore


class JobReturnCreateSchema(BaseModel, JobReturnReadOnlyFieldsMixin, JobReturnEditableFieldsMixin):
    model_config = ConfigDict(extra='allow')

    @model_validator(mode='before')
    @classmethod
    def _extract_kwargs[T](cls, data: T) -> T:
        # data may be an instantiated Job or potentially any object
        if not isinstance(data, dict):
            return data

        data['fun_args'], data['fun_kwarg'] = fill_salt_kwarg_from_arg(data.get('fun_args'), data.get('fun_kwarg'))

        return data


class JobReturnUpdateSchema(BaseModel, JobReturnEditableFieldsMixin):
    model_config = ConfigDict(extra='ignore')


class JobReturnModel(
    BaseModel,
    JobReturnComputedFieldsMixin,
    CreatedModifiedMixin,
    JobReturnReadOnlyFieldsMixin,
    JobReturnEditableFieldsMixin,
    IDMixin,
):
    data: Any = Field(default=None)


# REST


class JobReturnListResponse(
    BaseModel,
    JobReturnComputedFieldsMixin,
    CreatedModifiedMixin,
    JobReturnReadOnlyFieldsMixin,
    JobReturnEditableFieldsMixin,
    IDMixin,
):
    data: Any = Field(
        default=None
    )  # TODO @: Temporary. Remove this after front will be get this from job return endpoint
