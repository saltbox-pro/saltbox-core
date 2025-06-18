# FIXME US317
from saltbox_bridge_messages import BusMasterMessage


class PillarClearCacheMessage(BusMasterMessage):
    tgt: str
    tgt_type: str
