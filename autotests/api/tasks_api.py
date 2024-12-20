from api import routes


def get_tasks(client, page=0, per_page=20):
    params = {
        'page': page,
        'per_page': per_page,
    }
    params = {k: v for k, v in params.items() if v is not None}
    return client.request('GET', routes.Routes.TASKS, params=params)


def post_tasks(client, **kwargs):
    return client.request('POST', routes.Routes.TASKS, **kwargs)


def get_tasks_tid(client, tid):
    return client.request('GET', routes.Routes.TASKS_ID.format(tid))


def get_tasks_template(client, page=0, per_page=20):
    params = {
        'page': page,
        'per_page': per_page,
    }
    params = {k: v for k, v in params.items() if v is not None}
    return client.request('GET', routes.Routes.TASKS_TEMPLATE, params=params)


def post_tasks_template(client, **kwargs):
    return client.request('POST', routes.Routes.TASKS_TEMPLATE, **kwargs)


def get_tasks_template_tid(client, tid):
    return client.request('GET', routes.Routes.TASKS_TEMPLATE_ID.format(tid))


def put_tasks_template_tid(client, tid, **kwargs):
    return client.request('PUT', routes.Routes.TASKS_TEMPLATE_ID.format(tid), **kwargs)


def del_tasks_template_tid(client, tid):
    return client.request('DELETE', routes.Routes.TASKS_TEMPLATE_ID.format(tid))


def post_tasks_tid_run(client, tid):
    return client.request('POST', routes.Routes.TASKS_RUN.format(tid))


def post_tasks_tid_stop(client, tid):
    return client.request('POST', routes.Routes.TASKS_STOP.format(tid))
