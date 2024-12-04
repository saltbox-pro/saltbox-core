#! /bin/sh
set -e

warn() {
  1>&2 echo "$@"
}

SALT_PASSWORD="$(cat /run/secrets/salt_api_password)"
REDIS_PASSWORD="$(cat /run/secrets/redis_salt_password)"
MONGO_PASSWORD="$(cat /run/secrets/mongo_admin_password)"

CELERY_BROKER_URL="redis://${REDIS_CELERY_USERNAME}"
if [ -f "$REDIS_CELERY_PASSWORD_SECRET" ]; then
  redis_celery_password="$(cat "$REDIS_CELERY_PASSWORD_SECRET")"
  CELERY_BROKER_URL="${CELERY_BROKER_URL}:${redis_celery_password}"
else
  warn NOT PASSWORD FOR REDIS USER
fi

CELERY_BROKER_URL="${CELERY_BROKER_URL}@${REDIS_CELERY_HOST}:${REDIS_CELERY_PORT}"
CELERY_BROKER_URL="${CELERY_BROKER_URL}/${REDIS_CELERY_DB}"

export SALT_PASSWORD REDIS_PASSWORD MONGO_PASSWORD CELERY_BROKER_URL
