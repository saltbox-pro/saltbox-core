from jsonschema import Draft4Validator, validators


def extend_validator_with_default(validator_class: type[Draft4Validator]) -> type[Draft4Validator]:
    validate_properties = validator_class.VALIDATORS['properties']

    def set_defaults(validator, properties, instance, schema):  # type: ignore[no-untyped-def]
        valid = True
        for error in validate_properties(validator, properties, instance, schema):
            valid = False
            yield error

        if valid:
            for _property, _sub_schema in properties.items():
                if 'default' in _sub_schema and not isinstance(instance, list):
                    instance.setdefault(_property, _sub_schema['default'])

    return validators.extend(validator_class, {'properties': set_defaults})  # type: ignore[no-any-return]


Draft4ValidatorWithDefaults = extend_validator_with_default(Draft4Validator)
