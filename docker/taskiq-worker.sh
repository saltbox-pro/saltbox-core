#! /bin/sh
# shellcheck source=./shell_init.sh
. /etc/shell_init.sh

# -fsd - autodiscover tasks in all modules
# -tp - file pattern for autodiscover (default: **/tasks.py)
# -r - autoreload for dev
# -w - number of workers
# --max-fails - max number of failed tasks before stopping the worker

if [ -f "$DEBUG" ]; then
  cmd="taskiq worker -r salt_box_core.tkq:broker salt_box_core.jobs salt_box_core.settings -w 1 --max-fails 1"
else
  cmd="taskiq worker salt_box_core.tkq:broker salt_box_core.jobs.tasks salt_box_core.settings.tasks -w 1 --max-fails 1"
fi

echo "$ ${cmd}"
eval "$cmd"
