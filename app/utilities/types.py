from typing import Union
from typing_extensions import TypeAlias

Json: TypeAlias = Union[dict[str, 'Json'], list['Json'], str, int, float, bool, None]
