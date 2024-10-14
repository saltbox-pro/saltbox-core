from odmantic import Model
from odmantic.field import ODMEmbedded


def get_model_schema(model: Model, pre_path: str = None):
    schema = list()

    odm_fields = model.__odm_fields__

    for field_name, field in model.model_fields.items():
        full_field_name: str = f'{pre_path}.{field_name}' if pre_path else field_name
        odm_field = odm_fields.get(field_name)

        if isinstance(odm_field, ODMEmbedded):
            schema.extend(get_model_schema(odm_field.model, full_field_name))
        else:
            schema.append({
                'name': full_field_name,
                'label': field.title if field.title else full_field_name,
            })

    return schema
