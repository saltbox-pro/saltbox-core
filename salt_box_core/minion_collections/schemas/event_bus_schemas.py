from typing import Any

# FIXME US317
from saltbox_bridge_messages import BusMasterMessage


class GatherMinionsByTargeting(BusMasterMessage):
    tgt: str
    tgt_type: str


class MinionPresenceMessage(BusMasterMessage):
    minions: list[str]
    stamp: float


class MinionGrainsMessage(BusMasterMessage):
    grains: dict[str, Any]
