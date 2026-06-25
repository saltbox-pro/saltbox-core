import copy
from typing import Any

from jsonschema import Draft202012Validator, SchemaError

from saltbox_core.config import logger


class PillarSchemaUpdater:
    def __init__(self, schema: dict[str, Any]) -> None:
        self._original_schema = copy.deepcopy(schema)
        self._working_schema: dict[str, Any] = {}

    def set_defaults(self, pillar_defaults: dict[str, Any]) -> dict[str, Any]:
        schema = copy.deepcopy(self._original_schema)
        pillar_schema = self._get_pillar_schema(schema)

        if pillar_schema is not None:
            self._working_schema = schema
            self._update_node(pillar_schema, pillar_defaults)

        try:
            self._validate_schema(schema)
        except SchemaError as e:
            logger.exception('Updated schema is invalid: %s', e)
            return self._original_schema

        return schema

    def _get_pillar_schema(self, schema: dict[str, Any]) -> dict[str, Any] | None:
        try:
            pillar_schema: dict[str, Any] = schema['properties']['kwargs']['properties']['pillar']
            return pillar_schema
        except KeyError:
            return None

    def _resolve_ref(self, ref: str) -> dict[str, Any] | None:
        if not ref.startswith('#/definitions/'):
            return None
        def_name = ref[len('#/definitions/') :]
        definition = self._working_schema.get('definitions', {}).get(def_name)
        return definition if isinstance(definition, dict) else None

    def _update_node(self, node: dict[str, Any], defaults_map: dict[str, Any]) -> None:
        if ref := node.get('$ref'):
            resolved = self._resolve_ref(ref)
            if resolved is not None:
                self._update_node(resolved, defaults_map)

        self._process_properties(node, defaults_map)
        self._process_recursive_keywords(node, defaults_map)
        self._process_compositions(node, defaults_map)

    def _process_properties(self, node: dict[str, Any], defaults_map: dict[str, Any]) -> None:
        for name, prop in node.get('properties', {}).items():
            if not isinstance(prop, dict):
                continue
            if name in defaults_map:
                val = defaults_map[name]
                if isinstance(val, dict) and 'properties' in prop:
                    self._update_node(prop, val)
                else:
                    prop['default'] = val
                    if isinstance(val, dict):
                        self._update_node(prop, val)
            self._update_node(prop, defaults_map)

    def _process_recursive_keywords(self, node: dict[str, Any], defaults_map: dict[str, Any]) -> None:
        for kw in ('if', 'then', 'else', 'additionalProperties'):
            if isinstance(val := node.get(kw), dict):
                self._update_node(val, defaults_map)

        if items := node.get('items'):
            if isinstance(items, dict):
                self._update_node(items, defaults_map)
            elif isinstance(items, list):
                for item in items:
                    if isinstance(item, dict):
                        self._update_node(item, defaults_map)

    def _process_compositions(self, node: dict[str, Any], defaults_map: dict[str, Any]) -> None:
        for kw in ('allOf', 'anyOf', 'oneOf'):
            for sub in node.get(kw, []):
                if isinstance(sub, dict):
                    self._update_node(sub, defaults_map)

    def _validate_schema(self, schema: dict[str, Any]) -> None:
        Draft202012Validator.check_schema(schema)
