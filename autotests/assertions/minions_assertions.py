from api.minions_api import get_minion_collection_cid


def assertion_collection_title(api, response, created_mid):
    get_response = get_minion_collection_cid(api, created_mid)
    title_from_response = get_response.json().get('title')
    update_title = response.json().get('title')
    assert title_from_response == update_title, 'ERROR, COLLECTION IS NOT UPDATED'
