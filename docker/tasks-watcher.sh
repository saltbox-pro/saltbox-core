#! /bin/sh
set -e

application=fastms_core.celery

err() {
  2>&1 echo "$1" && exit 1
}

[ -n "$1" ] && err "Unknown arg \"$1\""

. export-secrets.sh

cmd="python3 /mnt/salt_box_core/fastms_core/tasks/tasks_watcher.py"

echo "$ ${cmd}"
eval "$cmd"
