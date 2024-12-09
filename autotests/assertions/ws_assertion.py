import asyncio
import pytest


async def wait_for_job_message(api, jid, timeout=50):
    """
    Waits for a job-related message to arrive via WebSocket.
    """
    try:
        message = await asyncio.wait_for(api.ws.listen().__anext__(), timeout=timeout)
        assert message['jid'] == jid
    except asyncio.TimeoutError:
        pytest.fail('Timeout: No message received from the server within the expected time.')
