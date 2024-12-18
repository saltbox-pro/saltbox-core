from api import routes


def post_minions(client, **kwargs):
    return client.request('POST', routes.Routes.MINIONS, **kwargs)


def get_minions_mid(client, mid):
    return client.request('GET', routes.Routes.MINIONS_ID.format(mid))
