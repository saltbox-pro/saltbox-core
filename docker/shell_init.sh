# This file is a part of salt.box core Docker image.
#
# This file supposed to be sourced with a shell.
#

set -e

warn() {
  1>&2 echo "$@"
}

err() {
  warn "$@" && exit 1
}

REDIS_PASSWORD="$(cat /run/secrets/redis_salt_password)"
MONGO_PASSWORD="$(cat /run/secrets/mongo_admin_password)"

TASKIQ_BROKER_URL="redis://${REDIS_TASKIQ_USERNAME}"
if [ -f "$REDIS_TASKIQ_PASSWORD_SECRET" ]; then
  redis_taskiq_password="$(cat "$REDIS_TASKIQ_PASSWORD_SECRET")"
  TASKIQ_BROKER_URL="${TASKIQ_BROKER_URL}:${redis_taskiq_password}"
else
  warn NOT PASSWORD FOR REDIS USER
fi

TASKIQ_BROKER_URL="${TASKIQ_BROKER_URL}@${REDIS_TASKIQ_HOST}:${REDIS_TASKIQ_PORT}"
TASKIQ_BROKER_URL="${TASKIQ_BROKER_URL}/${REDIS_TASKIQ_DB}"

export REDIS_PASSWORD MONGO_PASSWORD TASKIQ_BROKER_URL
