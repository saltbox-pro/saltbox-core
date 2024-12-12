import json
import os
import websockets

from base64 import b64encode
from httpx import Client, Response
from utilities.logger_utils import logger
from httpx import BasicAuth


class ApiClient(Client):

    def __init__(self):
        super().__init__(base_url=os.getenv("RESOURCE_URL"))
        self.ws = WsClient(base_url=os.getenv("RESOURCE_WS_URL"), api_client=self)
        self.token = None

    # @staticmethod
    # def basic_auth_header(self):
    #     """Return header for для Basic Auth."""
    #     username = os.getenv('BASIC_AUTH_LOGIN')
    #     password = os.getenv('BASIC_AUTH_PASSWORD')
    #     return f"Basic {b64encode(f'{username}:{password}'.encode()).decode()}"

    def get_token(self):
        """Get Bearer Token."""
        url = os.getenv('GET_TOKEN_ENDPOINT')
        payload = {
            'username': os.getenv('USER_NAME'),
            'password': os.getenv('USER_PASSWORD'),
            'grant_type': 'password',
            'client_id': 'fastms_core',
            'client_secret': os.getenv('CLIENT_SECRET'),
            'scope': 'openid',
        }
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
        }

        response = super().request('POST', url, data=payload, headers=headers,
                                   auth=BasicAuth(os.getenv('BASIC_AUTH_LOGIN'), os.getenv('BASIC_AUTH_PASSWORD')))
        response.raise_for_status()
        logger.info('Token successfully retrieve')
        return response.json().get('access_token')

    def request(self, method, url, **kwargs) -> Response:
        """Requests with auth token"""
        if not self.token:
            self.token = self.get_token()

        # Update request headers
        headers = kwargs.pop("headers", {}) or {}
        headers.update({
            'Authorization': f'Bearer {self.token}'
        })
        kwargs['headers'] = headers

        # Logger
        self.log_request(method, url, **kwargs)

        return super().request(method, url, **kwargs)

    @staticmethod
    def log_request(method, url, **kwargs):
        """Logging request info."""
        if eval(os.getenv('LOGGING')):
            log_message = f"{method} {url}"
            if kwargs.get('params'):
                log_message += f" | Params: {json.dumps(kwargs['params'])}"
            if kwargs.get('json'):
                log_message += f" | Body: {json.dumps(kwargs['json'])}"
            logger.info(log_message)


class WsClient:
    def __init__(self, base_url, api_client):
        self.base_url = base_url
        self.api_client = api_client
        self.websocket = None

    async def connect(self, endpoint):
        headers = {
            'Authorization': f'Bearer {self.api_client.token}'  # Используем токен ApiClient
        }
        if eval(os.getenv('USE_BASIC_AUTH')):
            username = os.getenv('BASIC_AUTH_LOGIN')
            password = os.getenv('BASIC_AUTH_PASSWORD')
            auth_header = f"Basic {b64encode(f'{username}:{password}'.encode()).decode()}"
            headers["Authorization"] = auth_header
        self.websocket = await websockets.connect(f'{self.base_url}{endpoint}', extra_headers=headers)

    async def send(self, message):
        await self.websocket.send(json.dumps(message))

    async def receive(self):
        message = await self.websocket.recv()
        return json.loads(message)

    async def listen(self):
        async for message in self.websocket:
            data = json.loads(message)
            yield data

    async def close(self):
        await self.websocket.close()
