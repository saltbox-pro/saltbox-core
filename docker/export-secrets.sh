#! /bin/sh
set -e

SALT_PASSWORD="$(cat /run/secrets/salt_api_password)"
REDIS_PASSWORD="$(cat /run/secrets/redis_salt_password)"
MONGO_PASSWORD="$(cat /run/secrets/mongo_admin_password)"
export SALT_PASSWORD REDIS_PASSWORD MONGO_PASSWORD
