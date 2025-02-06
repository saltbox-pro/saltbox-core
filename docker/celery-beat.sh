#! /bin/sh
# shellcheck source=./shell_init.sh
. /etc/shell_init.sh

application=salt_box_core.celery

[ -n "$1" ] && err "Unknown arg \"$1\""

cmd="celery --app='${application}' beat"

echo "$ ${cmd}"
eval "$cmd"
