from __future__ import annotations

import json
from typing import Any

from redis import exceptions as redis_exceptions
from redis.asyncio import Redis

from fastms_core.db.redis import POOL
from fastms_core.utilities.jid import JID


def fill_salt_kwarg_from_arg(
    arg: None | list[Any], kwarg: None | dict[str, Any]
) -> tuple[None | list[Any], None | dict[str, Any]]:
    """
    Extract kwarg dicts from args for SaltStack messages

    SaltStack has *args, **kwargs ideom, but often puts kwargs in args list as
    an object with the special `__kwarg__: True` key. Function make "canonical"
    args and kwargs.

    :param arg: list of args e.g. from job/*/ret message
    :param kwarg: dict of kwargs e.g. from job/*/ret message
    :return: updated list of args and dict of kwargs
    """

    def is_kwargs(val: Any) -> bool:
        return isinstance(val, dict) and '__kwarg__' in val

    if not arg or not (extracted_kwargs := list(filter(is_kwargs, arg))):
        return arg, kwarg

    new_arg = list(filter(lambda val: not is_kwargs(val), arg))

    new_kwarg = {}
    if kwarg:
        new_kwarg.update(kwarg)

    for kwarg_dict in extracted_kwargs:
        kwarg_dict.pop('__kwarg__')
        new_kwarg.update(kwarg_dict)

    return new_arg, new_kwarg


class SaltJobCreateError(Exception): ...


async def create_job(
    tgt: str,
    tgt_type: str,
    fun: str,
    arg: list | None = None,
    kwarg: dict | None = None,
    jid: str | None = None,
    jid_postfix: str | None = None,
    salt_master: str | None = None,
    rdb: Redis | None = None,
) -> str:
    if not rdb:
        rdb = Redis(connection_pool=POOL)

    if not jid:
        jid = str(JID.generate())

    create_job_hash_name: str = f'job_create:{jid}'

    try:
        await rdb.hmset(
            name=create_job_hash_name,
            mapping={
                'jid': f'{jid}-{jid_postfix}' if jid_postfix else jid,
                'fun': fun,
                'tgt': tgt,
                'tgt_type': tgt_type,
                'arg': json.dumps(arg),
                'kwarg': json.dumps(kwarg),
            },
        )

        await rdb.publish(
            channel='salt-service',
            message=json.dumps(
                {
                    'command': f'job/run/{salt_master}' if salt_master else 'job/run',
                    'payload': {
                        'hash_name': create_job_hash_name,
                    },
                }
            ),
        )
    except redis_exceptions.RedisError as error:
        raise SaltJobCreateError(error) from error

    await rdb.aclose()  # type: ignore

    return jid
