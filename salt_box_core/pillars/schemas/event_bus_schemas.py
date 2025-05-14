from salt_box_core.event_bus.master_bus_base_messages import BusMasterMessage


class PillarClearCacheMessage(BusMasterMessage):
    tgt: str
    tgt_type: str
