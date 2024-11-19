#! /bin/sh
set -e

extra_args=''

case $1 in
  start) ;;
  dev) extra_args='--reload' ;;
  *) echo "unknown command \"$1\"" && exit 1 ;;
esac

SALT_PASSWORD="$(cat /run/secrets/salt_api_password)"
REDIS_PASSWORD="$(cat /run/secrets/redis_salt_password)"
MONGO_PASSWORD="$(cat /run/secrets/mongo_admin_password)"
export SALT_PASSWORD REDIS_PASSWORD MONGO_PASSWORD

cmd='uvicorn fastms_core.main:APP'
cmd="$cmd --host=0.0.0.0 --port=8000 --root-path='${BASE_URL_ROOT_PATH}'"
cmd="$cmd --timeout-graceful-shutdown='${TIMEOUT_GRACEFUL_SHUTDOWN}'"
cmd="$cmd $extra_args"

echo "$ $cmd"
eval "$cmd"
