from api import routes


def get_minions(client, page=0, per_page=20, query=None):
    params = {
        'page': page,
        'per_page': per_page,
        'query': query,
    }
    params = {k: v for k, v in params.items() if v is not None}
    return client.get(routes.Routes.MINIONS, params=params)


def get_minions_filter_schema(client):
    return client.get(routes.Routes.MINIONS_FILTER_SCHEMA)


def get_minions_mid(client, mid):
    return client.get(routes.Routes.MINIONS_ID.format(mid))
