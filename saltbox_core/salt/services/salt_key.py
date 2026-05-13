import asyncio
from typing import Annotated, Any, ClassVar, Literal, overload

from fastapi import Depends

from saltbox_bridge_messages import (
    CoreMessageBase,
    SaltKeysRequest,
    SaltKeysResponse,
    SaltKeyStatusType,
    SaltListKeysRequest,
    SaltListKeysResponse,
)
from saltbox_core.config import logger
from saltbox_core.event_bus.redis.app import get_faststream_broker
from saltbox_core.event_bus.redis.masters_bus import send_message_and_wait_response_to_master
from saltbox_core.masters.exceptions import TimeoutResponseToMasterException
from saltbox_core.masters.schemas.master_schemas import MasterMasterIdOnlySchema
from saltbox_core.masters.services.master_service import MasterService, get_master_service
from saltbox_core.salt.schemas.salt_keys import (
    SaltKeyActionEnum,
    SaltKeyMinion,
    SaltKeyMinionWithStatus,
    SaltKeyToUpdateStatusEnum,
    SaltKeyUpdateResultSchema,
)


class SaltKeysService:
    def __init__(self, master_service: MasterService) -> None:
        self.master_service = master_service

    ACTIONS_TO_PARTIAL_MESSAGE_TAGS_MAP: ClassVar[dict[SaltKeyActionEnum, str]] = {
        SaltKeyActionEnum.accept: 'accept_keys',
        SaltKeyActionEnum.reject: 'reject_keys',
        SaltKeyActionEnum.delete: 'delete_keys',
    }

    ACTIONS_TO_ALL_MESSAGE_TAGS_MAP: ClassVar[dict[SaltKeyActionEnum, str]] = {
        SaltKeyActionEnum.accept: 'accept_all_keys',
        SaltKeyActionEnum.reject: 'reject_all_keys',
        SaltKeyActionEnum.delete: 'delete_all_keys',
    }

    ACTIONS_TO_NEW_STATUS_MAP: ClassVar[dict[SaltKeyActionEnum, SaltKeyToUpdateStatusEnum]] = {
        SaltKeyActionEnum.accept: SaltKeyToUpdateStatusEnum.accepted,
        SaltKeyActionEnum.reject: SaltKeyToUpdateStatusEnum.rejected,
    }

    async def _parse_action_result(
        self, results_from_masters: list[SaltKeysResponse | None], action: SaltKeyActionEnum
    ) -> SaltKeyUpdateResultSchema | None:
        if action == SaltKeyActionEnum.delete:
            return None

        updated_minions: list[SaltKeyMinion] = []

        for result_from_master in results_from_masters:
            if result_from_master is None:
                continue

            for minion_id in result_from_master.minions:
                updated_minions.append(SaltKeyMinion(minion_id=minion_id, salt_master=result_from_master.master))

        return SaltKeyUpdateResultSchema(minions=updated_minions, new_key_status=self.ACTIONS_TO_NEW_STATUS_MAP[action])

    @staticmethod
    async def _send_action_on_salt_key_to_master(
        message: SaltKeysRequest | CoreMessageBase, message_tag: str
    ) -> SaltKeysResponse | None:
        try:
            return SaltKeysResponse.model_validate(
                await send_message_and_wait_response_to_master(
                    message=message,
                    message_tag=message_tag,
                    broker=get_faststream_broker(),
                )
            )
        except TimeoutResponseToMasterException:
            return None

    @overload
    async def _action_on_salt_key(
        self,
        action: Literal[SaltKeyActionEnum.accept, SaltKeyActionEnum.reject],
        minions: list[SaltKeyMinion] | None = None,
        masters: list[str] | None = None,
    ) -> SaltKeyUpdateResultSchema: ...

    @overload
    async def _action_on_salt_key(
        self,
        action: Literal[SaltKeyActionEnum.delete],
        minions: list[SaltKeyMinion] | None = None,
        masters: list[str] | None = None,
    ) -> None: ...

    async def _action_on_salt_key(
        self, action: SaltKeyActionEnum, minions: list[SaltKeyMinion] | None = None, masters: list[str] | None = None
    ) -> SaltKeyUpdateResultSchema | None:
        messages_to_masters: list[SaltKeysRequest | CoreMessageBase] = []

        if minions is not None and masters is not None:
            msg = 'Cannot specify both minions and masters'
            raise ValueError(msg)
        elif minions is not None:
            message_tag = self.ACTIONS_TO_PARTIAL_MESSAGE_TAGS_MAP[action]
            minions_by_masters: dict[str, list[str]] = {}

            for minion in minions:
                minions_by_masters.setdefault(minion.salt_master, []).append(minion.minion_id)

            for salt_master, minions_on_master in minions_by_masters.items():
                messages_to_masters.append(SaltKeysRequest(master=salt_master, minions=minions_on_master))
        else:
            message_tag = self.ACTIONS_TO_ALL_MESSAGE_TAGS_MAP[action]
            masters_query: dict[str, Any] = {'status': 'accepted'}

            if masters is not None:
                masters_query['master_id'] = {'$in': masters}

            logger.warning(masters_query)
            logger.warning(masters)

            masters_objs = await self.master_service.get_list(
                query=masters_query, skip=0, limit=0, projection_model=MasterMasterIdOnlySchema
            )

            logger.warning(masters_objs)

            for salt_master_obj in masters_objs:
                messages_to_masters.append(CoreMessageBase(master=salt_master_obj.master_id))

        tasks: list[asyncio.Task] = []

        for message_to_master in messages_to_masters:
            tasks.append(
                asyncio.create_task(
                    self._send_action_on_salt_key_to_master(message=message_to_master, message_tag=message_tag)
                )
            )

        return await self._parse_action_result(results_from_masters=await asyncio.gather(*tasks), action=action)

    async def accept_keys(self, minions: list[SaltKeyMinion]) -> SaltKeyUpdateResultSchema:
        return await self._action_on_salt_key(action=SaltKeyActionEnum.accept, minions=minions)

    async def reject_keys(self, minions: list[SaltKeyMinion]) -> SaltKeyUpdateResultSchema:
        return await self._action_on_salt_key(action=SaltKeyActionEnum.reject, minions=minions)

    async def delete_keys(self, minions: list[SaltKeyMinion]) -> None:
        return await self._action_on_salt_key(action=SaltKeyActionEnum.delete, minions=minions)

    async def accept_all_keys(self, masters: list[str] | None = None) -> SaltKeyUpdateResultSchema:
        return await self._action_on_salt_key(action=SaltKeyActionEnum.accept, masters=masters)

    async def reject_all_keys(self, masters: list[str] | None = None) -> SaltKeyUpdateResultSchema:
        return await self._action_on_salt_key(action=SaltKeyActionEnum.reject, masters=masters)

    async def delete_all_keys(self, masters: list[str] | None = None) -> None:
        return await self._action_on_salt_key(action=SaltKeyActionEnum.delete, masters=masters)

    @staticmethod
    async def _get_salt_keys_from_master(
        master: str, status: SaltKeyStatusType | None = None
    ) -> SaltListKeysResponse | None:
        try:
            return SaltListKeysResponse.model_validate(
                await send_message_and_wait_response_to_master(
                    message=SaltListKeysRequest(master=master, status=status),
                    message_tag='list_keys',
                    broker=get_faststream_broker(),
                )
            )
        except TimeoutResponseToMasterException:
            return None

    async def list_keys(
        self, masters: list[str] | None = None, status: SaltKeyStatusType | None = None
    ) -> list[SaltKeyMinionWithStatus]:
        result: list[SaltKeyMinionWithStatus] = []
        tasks: list[asyncio.Task] = []
        masters_query: dict[str, Any] = {'status': 'accepted'}

        if masters:
            masters_query['master_id'] = {'$in': masters}

        masters_objs = await self.master_service.get_list(
            query=masters_query, skip=0, limit=0, projection_model=MasterMasterIdOnlySchema
        )

        for salt_master_obj in masters_objs:
            tasks.append(
                asyncio.create_task(self._get_salt_keys_from_master(master=salt_master_obj.master_id, status=status))
            )

        requests_from_masters: list[SaltListKeysResponse | None] = await asyncio.gather(*tasks)

        for request_from_master in requests_from_masters:
            if request_from_master is None:
                continue

            for salt_key_status, minions_by_status in request_from_master.salt_keys.items():
                for minion in minions_by_status:
                    result.append(
                        SaltKeyMinionWithStatus(
                            minion_id=minion, salt_master=request_from_master.master, status=salt_key_status
                        )
                    )

        return result


def get_salt_key_service(
    master_service: Annotated[MasterService, Depends(get_master_service)],
) -> SaltKeysService:
    return SaltKeysService(master_service=master_service)
