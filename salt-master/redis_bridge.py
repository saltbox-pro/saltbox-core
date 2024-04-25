"""
В конфиг мастера:

    module_dirs:
      - /srv/salt_extmod/  # Произвольная доп. директория с модулями для мастера.
                           # Не стоит смешивать с /srv/salt/

    engines:
      - redis_bridge:  # Дальше идут аргументы для start()
          host: localhost  # Тут будет fastms-redis для контейнеров

Модуль разместить в указанной в module_dirs директории в поддиректории enines:
/srv/salt_extmod/engines/redis_bridge.py

Рестартнуть salt-master. Журнал и исключения будут в журнале salt-master.

"""

import logging
import re

from typing import Optional, Union

import redis

from salt.utils.event import get_master_event
from salt.utils import json

LOGGER = logging.getLogger(__name__)


def __virtual__() -> Union[bool, tuple[bool, str]]:
    if __opts__['__role'] != 'master':
        return (False, f'{__name__} runs on master only')
    return True


class RedisPusher:
    def __init__(self, host: str, port: int, db: int) -> None:
        self.redis = redis.Redis(host=host, port=port, db=db)

    def process(self, event: Optional[dict]) -> None:
        # TODO Make separate tag handlers
        if not event:
            return

        tag_new = re.compile(r'salt/job/(?P<jid>[\d]{20})/new')
        tag_ret = re.compile(r'salt/job/(?P<jid>[\d]{20})/ret/(?P<mid>.+)')

        tag = event['tag']
        body = json.dumps(event['data'])

        LOGGER.debug('%s got event with tag "%s"', __name__, tag)

        match = tag_new.match(tag)
        if match:
            # Наблюдение: при вызове salt-call события salt/job/*/new нет
            # (а salt/job/*/ret/* есть)
            jid = match.group('jid')
            LOGGER.info('New job: %s', jid)
            # self.redisset(name=f'job:{jid}', value=body)
            self.redis.zadd(name='jobs', mapping={body: int(jid)})
            self.redis.publish(channel=f'job:{jid}', message=body)
            return

        match = tag_ret.match(tag)
        if match:
            jid = match.group('jid')
            mid = match.group('mid')
            LOGGER.info('New job return: %s: %s', jid, mid)

            self.redis.hset(name=f'job.rets:{jid}', key=mid, value=body)
            self.redis.publish(channel=f'job.rets:{jid}', message=body)
            return


def start(host='localhost', port=6379, db=0) -> None:
    sock_dir = __opts__['sock_dir']
    pusher = RedisPusher(host=host, port=port, db=db)

    with get_master_event(__opts__, sock_dir, listen=True) as event_bus:
        while True:
            pusher.process(event_bus.get_event(full=True))
