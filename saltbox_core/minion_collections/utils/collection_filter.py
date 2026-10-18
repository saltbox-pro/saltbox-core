from collections.abc import Hashable, Iterable, Mapping
from typing import Any

from saltbox_sdk.exceptions import SaltBoxValidationException

COLLECTION_FILTER_FIELD = 'collection'
COLLECTION_FILTER_LOOKUPS = ('$in', '$nin')


def parse_collection_filter(value: Any) -> tuple[str, list[str]]:
    if isinstance(value, dict) and len(value) == 1:
        lookup, slugs = next(iter(value.items()))

        if (
            lookup in COLLECTION_FILTER_LOOKUPS
            and isinstance(slugs, list)
            and all(isinstance(slug, str) for slug in slugs)
        ):
            return lookup, slugs

    msg = f'Field `{COLLECTION_FILTER_FIELD}` supports only `$in` and `$nin` operators with a list of collection slugs'
    raise SaltBoxValidationException(msg)


def get_referenced_slugs(query: Any) -> set[str]:
    slugs: set[str] = set()

    if isinstance(query, dict):
        for key, value in query.items():
            if key == COLLECTION_FILTER_FIELD:
                slugs.update(parse_collection_filter(value)[1])
            else:
                slugs.update(get_referenced_slugs(value))
    elif isinstance(query, list):
        for item in query:
            slugs.update(get_referenced_slugs(item))

    return slugs


def find_cycle[K: Hashable](start: K, edges: Mapping[K, Iterable[K]]) -> list[K] | None:
    path = [start]
    checked = {start}

    def walk(node: K) -> list[K] | None:
        for next_node in edges.get(node, ()):
            if next_node == start:
                return [*path, start]
            if next_node in checked:
                continue

            checked.add(next_node)
            path.append(next_node)
            if cycle := walk(next_node):
                return cycle
            path.pop()

        return None

    return walk(start)
