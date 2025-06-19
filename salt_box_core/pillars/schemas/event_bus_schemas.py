# FIXME US317
from saltbox_bridge_messages import CoreMessageBase


class PillarClearCacheMessage(CoreMessageBase):
    tgt: str
    tgt_type: str
