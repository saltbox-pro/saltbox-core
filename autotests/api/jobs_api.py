from api import routes


def get_jobs(client, start_datetime, end_datetime=None):
    params = {'start_datetime': start_datetime}
    if end_datetime:
        params['end_datetime'] = end_datetime
    return client.get(routes.Routes.JOBS, params=params)


def get_jobs_jid(client, jid):
    return client.get(routes.Routes.JOB_JID.format(jid))


def get_jobs_jid_return(client, jid, count=None, cursor=None):
    params = {
        'count': count,
        'cursor': cursor,
    }
    params = {k: v for k, v in params.items() if v is not None}
    return client.get(routes.Routes.JOB_RETURN.format(jid), params=params)


def get_jobs_jid_returns_count(client, jid):
    return client.get(routes.Routes.JOB_RETURNS_COUNT.format(jid))


def post_jobs(clietn, **kwargs):
    return clietn.post(routes.Routes.JOBS, **kwargs)


def ws_jobs(client):
    return client.ws.connect(routes.Routes.JOBS)


def ws_jobs_return(client, jid):
    return client.ws.connect(routes.Routes.JOB_RETURN.format(jid))
