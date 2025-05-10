#! /bin/sh
# shellcheck source=./shell_init.sh
. /etc/shell_init.sh

extra_args=''

case $1 in
  start) ;;
  dev) extra_args='--reload' ;;
  *) echo "unknown command \"$1\"" && exit 1 ;;
esac

cmd='/usr/bin/uvicorn salt_box_core.main:app'
cmd="$cmd --host=0.0.0.0 --port=8000"
cmd="$cmd --timeout-graceful-shutdown=${TIMEOUT_GRACEFUL_SHUTDOWN}"
cmd="$cmd $extra_args"

echo "$ ${cmd}"
exec $cmd
