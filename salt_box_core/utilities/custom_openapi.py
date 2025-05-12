from typing import Any

from fastapi.openapi.utils import get_openapi

from salt_box_core.config import SETTINGS, logger


def get_custom_openapi_schema(
    app_configs: dict[str, Any],
    routes: list,
    servers: list,
) -> dict:
    """Generate a custom OpenAPI schema for the FastAPI application.
    This function customizes the OpenAPI schema by adding security schemes,
    external documentation, and other relevant information.
    It uses the Keycloak OIDC configuration for OAuth2 authentication.

    Args:
        app_configs (dict): Application configuration settings.
        routes (list): List of FastAPI routes.
        servers (list): List of server configurations.
    Returns:
        dict: Custom OpenAPI schema.
    """

    logger.debug('KeycloakOIDC in get_custom_openapi_schema.')
    oauth2_scheme = {
        'type': 'oauth2',
        'flows': {
            'authorizationCode': {
                'authorizationUrl': SETTINGS.keycloak_authorization_endpoint,
                'tokenUrl': SETTINGS.keycloak_token_url,
                'scopes': {'openid': 'OpenID Connect scope'},
            }
        },
    }

    openapi_schema = get_openapi(
        title=app_configs['title'],
        version=app_configs['version'],
        description=app_configs['description'],
        routes=routes,
        servers=servers,
    )
    openapi_schema['components']['securitySchemes'] = {'KeycloakOIDC': oauth2_scheme}
    openapi_schema['security'] = [{'KeycloakOIDC': []}]
    openapi_schema['externalDocs'] = {
        'description': 'Official Salt.Box documentation',
        'url': 'https://saltbox.pro',
    }

    return openapi_schema
