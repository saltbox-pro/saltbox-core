#! /bin/sh
# shellcheck source=./shell_init.sh
. /etc/shell_init.sh

# -fsd - autodiscover tasks in all modules
# -fp - file pattern for autodiscover (default: **/tasks.py)
# --skip-first-run - scheduler will wait until the start of the next minute and then start executing tasks

# cmd="taskiq scheduler -tp **/tasksq.py salt_box_core.tkq_sched:scheduler salt_box_core.async_tasks" # bad
# cmd="taskiq scheduler -tp **/tasksq.py salt_box_core.tkq_sched:scheduler salt_box_core.async_tasks.tasksq" # good

cmd="/usr/bin/taskiq scheduler salt_box_core.tkq_sched:scheduler salt_box_core.jobs.tasks"

echo "$ ${cmd}"
exec $cmd
