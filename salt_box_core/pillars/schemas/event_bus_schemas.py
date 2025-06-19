# FIXME US317
from saltbox_bridge_messages import BusMasterMessageBase


class PillarClearCacheMessage(BusMasterMessageBase):
    tgt: str
    tgt_type: str
