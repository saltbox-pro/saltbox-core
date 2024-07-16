import allure
import pytest
import requests
import os


class APIClient:
    def __init__(self, base_url):
        self.base_url = base_url

    def get(self, endpoint, params=None, headers=None):
        url = f'{self.base_url}{endpoint}'
        with allure.step(f'Sending GET request to url: {url}'):
            return requests.get(url=url, params=params, headers=headers)

    def post(self, endpoint, params=None, headers=None, json=None, data=None):
        url = f'{self.base_url}{endpoint}'
        with allure.step(f'Sending POST request to url: {url}'):
            return requests.post(url=url, params=params, headers=headers, json=json, data=data)


@pytest.fixture(scope='module')
def api():
    base_url = os.environ.get('FASTMS_CORE_URL', 'http://localhost:8000')
    return APIClient(base_url=base_url)


@pytest.fixture(scope='module')
def create_jid(api):
    payload = {
        'tgt': '*',
        'tgt_type': 'glob',
        'fun': 'test_api.ring',
        'arg': [],
        'kwarg': {}
    }
    response_json = api.post('/jobs', json=payload).json()
    jid = response_json['return'][0]['jid']
    return jid
