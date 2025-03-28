#! /bin/sh
# shellcheck source=./shell_init.sh
. /etc/shell_init.sh

# -fsd - autodiscover tasks in all modules
# -tp - file pattern for autodiscover (default: **/tasks.py)
# -r - autoreload for dev
# -w - number of workers
# --max-fails - max number of failed tasks before stopping the worker
cmd="taskiq worker -r salt_box_core.tkq:broker salt_box_core.async_tasks salt_box_core.jobs salt_box_core.settings -w 1 --max-fails 1"

echo "$ ${cmd}"
eval "$cmd"
