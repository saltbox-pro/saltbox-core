from api import routes


def get_minions_filter_schema(client):
    return client.request('GET', routes.Routes.MINIONS_FILTER_SCHEMA)


def post_minions_filter_values(client, **kwargs):
    return client.request('POST', routes.Routes.MINIONS_FILTER_VALUES, **kwargs)


def get_minions_collection(client, page=0, per_page=20):
    params = {
        'page': page,
        'per_page': per_page,
    }
    params = {k: v for k, v in params.items() if v is not None}
    return client.request('GET', routes.Routes.MINIONS_COLLECTION, params=params)


def post_minions_collection(client, **kwargs):
    return client.request('POST', routes.Routes.MINIONS_COLLECTION, **kwargs)


def get_minion_collection_cid(client, cid):
    return client.request('GET', routes.Routes.MINIONS_COLLECTION_ID.format(cid))


def put_minion_collection_cid(client, cid, **kwargs):
    return client.request('PUT', routes.Routes.MINIONS_COLLECTION_ID.format(cid), **kwargs)


def del_minion_collection_cid(client, cid):
    return client.request('DELETE', routes.Routes.MINIONS_COLLECTION_ID.format(cid))

# def get_minions(client, page=0, per_page=20, query=None):
#     params = {
#         'page': page,
#         'per_page': per_page,
#         'query': query,
#     }
#     params = {k: v for k, v in params.items() if v is not None}
#     return client.get(routes.Routes.MINIONS, params=params)


def post_minions(client, **kwargs):
    return client.request('POST', routes.Routes.MINIONS, **kwargs)


def get_minions_mid(client, mid):
    return client.request('GET', routes.Routes.MINIONS_ID.format(mid))
