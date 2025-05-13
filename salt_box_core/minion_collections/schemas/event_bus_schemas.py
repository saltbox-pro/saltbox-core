from typing import Any

from salt_box_core.event_bus.maater_bus_base_messages import BusMasterMessage


class GatherMinionsByTargeting(BusMasterMessage):
    tgt: str
    tgt_type: str


class MinionPresenceMessage(BusMasterMessage):
    minions: list[str]
    stamp: float


class MinionGrainsMessage(BusMasterMessage):
    grains: dict[str, Any]
