#! /bin/sh
set -e

extra_args=''

case $1 in
  start) ;;
  dev) extra_args='--reload' ;;
  *) echo "unknown command \"$1\"" && exit 1 ;;
esac

. export-secrets.sh

cmd='uvicorn fastms_core.main:APP'
cmd="$cmd --host=0.0.0.0 --port=8000 --root-path='${BASE_URL_ROOT_PATH}'"
cmd="$cmd --timeout-graceful-shutdown='${TIMEOUT_GRACEFUL_SHUTDOWN}'"
cmd="$cmd $extra_args"

echo "$ ${cmd}"
eval "$cmd"
