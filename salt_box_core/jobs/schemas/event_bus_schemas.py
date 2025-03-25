from salt_box_core.event_bus.masters_bus import BusMasterMessage


class NewJobMessage(BusMasterMessage):
    hash_name: str
