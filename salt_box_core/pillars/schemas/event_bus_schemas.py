from salt_box_core.event_bus.masters_bus import BusMasterMessage


class PillarClearCacheMessage(BusMasterMessage):
    tgt: str
    tgt_type: str
