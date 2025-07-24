from typing import TypeAlias

Json: TypeAlias = dict[str, 'Json'] | list['Json'] | str | int | float | bool | None
