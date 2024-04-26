import json
import logging
import re

import redis
from salt.config import client_config
from salt.utils.event import MasterEvent

logging.basicConfig()
logging.getLogger().setLevel(logging.DEBUG)
logger = logging.getLogger(__name__)
c_handler = logging.StreamHandler()
c_format = logging.Formatter('%(name)s - %(levelname)s - %(message)s')
c_handler.setFormatter(c_format)
logger.addHandler(c_handler)


#REDIS_HOST = 'fastms-redis'
REDIS_HOST = 'localhost'

r = redis.Redis(host=REDIS_HOST, port=6379, db=0)

opts = client_config('/etc/salt/master')
event = MasterEvent(
    sock_dir=opts['sock_dir'],
    opts=opts,
    listen=True,
    io_loop=None,
    keep_loop=False,
    raise_errors=False)

event_iterator = event.iter_events(full=True)

tag_new = r'salt/job/(?P<jid>[\d]{20})/new'
tag_ret = r'salt/job/(?P<jid>[\d]{20})/ret/(?P<mid>.+)'

logger.info('Start event bus')
for data in event_iterator:
    logger.info('CHECK')  # FIXME
    tag = data['tag']
    body = json.dumps(data['data'])

    logger.debug(tag)

    match = re.compile(tag_new).match(tag)
    if match:
        jid = match.group('jid')
        logger.info(f'new job: {jid}')
        # r.set(name=f'job:{jid}', value=body)
        r.zadd(name='jobs', mapping={body: int(jid)})
        r.publish(channel=f'job:{jid}', message=body)

    match = re.compile(tag_ret).match(tag)
    if match:
        jid = match.group('jid')
        mid = match.group('mid')
        logger.info(f'new job return: {jid}: {mid}')

        r.hset(name=f'job.rets:{jid}', key=mid, value=body)
        r.publish(channel=f'job.rets:{jid}', message=body)
