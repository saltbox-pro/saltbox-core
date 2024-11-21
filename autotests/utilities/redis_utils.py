import json
import os
import redis
from dotenv import load_dotenv

load_dotenv()
redis_host = os.getenv('REDIS_HOST', 'localhost')
redis_port = int(os.getenv('REDIS_PORT', 6379))
redis_db = int(os.getenv('REDIS_DB', 0))

# Connect to Redis
redis_client = redis.Redis(host=redis_host, port=redis_port, db=redis_db)


def decode_redis_hash(redis_data):
    decoded_data = {key.decode('utf-8'): json.loads(value.decode('utf-8')) for key, value in redis_data.items()}
    return decoded_data


def delete_job_from_zset_on_redis(jid):
    jobs_list_from_redis = redis_client.zrange('jobs', 0, -1)

    for e in jobs_list_from_redis:
        element_str = e.decode('utf-8')
        try:
            element_dict = json.loads(element_str)
        except json.JSONDecodeError:
            print(f'Error to decode element to JSON: {element_str}')
            continue

        if element_dict.get('jid') == jid:
            redis_client.zrem('jobs', element_str)
            return
