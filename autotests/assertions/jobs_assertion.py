from api.jobs_api import get_jobs_jid_return
from assertions.assertion_base import LogMsg


class JidValueLogMsg(LogMsg):
    def __init__(self, response):
        super().__init__('JID DOES NOT MATCH THE JID IN THE RESPONSE BODY', response)

    def add_compare_result(self, exp, act):
        """
        adds information about comparing the values of the jid field in the response
        :param exp: expected value
        :param act: actual value
        """

        self._msg += f'{self._where}\n'
        self._msg += f'\texpected JID: {exp}\n\tactual JID: {act}\n'
        return self


def assert_jid_in_response(jid, response, text=None):
    actual_jid = response.json()['jid']
    assert jid == actual_jid, JidValueLogMsg(response) \
        .add_error_info(text) \
        .add_compare_result(jid, actual_jid) \
        .add_request_url() \
        .add_response_info() \
        .get_message()


def assert_count(api, response, jid):
    assert isinstance(response.json(), int)
    response_for_count = get_jobs_jid_return(api, jid).json()
    assert 'result' in response_for_count, 'Response does not contain "result" key'
    result_count = len(response_for_count['result'])
    assert result_count == response.json(), 'The count of responses differs from the int returned by the API'
