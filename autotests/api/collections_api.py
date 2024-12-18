from api import routes


def get_collection(client, page=0, per_page=20):
    params = {
        'page': page,
        'per_page': per_page,
    }
    params = {k: v for k, v in params.items() if v is not None}
    return client.request('GET', routes.Routes.COLLECTION, params=params)


def post_collection(client, **kwargs):
    return client.request('POST', routes.Routes.COLLECTION, **kwargs)


def get_collection_cid(client, cid):
    return client.request('GET', routes.Routes.COLLECTION_ID.format(cid))


def put_collection_cid(client, cid, **kwargs):
    return client.request('PUT', routes.Routes.COLLECTION_ID.format(cid), **kwargs)


def del_collection_cid(client, cid):
    return client.request('DELETE', routes.Routes.COLLECTION_ID.format(cid))
