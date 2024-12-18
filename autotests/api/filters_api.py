from api import routes


def get_filter_schema(client):
    return client.request('GET', routes.Routes.FILTER_SCHEMA)


def post_filter_values(client, **kwargs):
    return client.request('POST', routes.Routes.FILTER_VALUES, **kwargs)
