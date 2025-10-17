#! /bin/sh

set -e

warn() {
  1>&2 echo "$@"
}

err() {
  warn "$@" && exit 1
}

REDIS_PASSWORD="$(cat /run/secrets/redis_salt_password)"
MONGO_PASSWORD="$(cat /run/secrets/mongo_admin_password)"
KEYCLOAK_CLIENT_SECRET="$(cat "$KEYCLOAK_CLIENT_SECRET_FILE")"

TASKIQ_BROKER_URL="redis://${REDIS_TASKIQ_USERNAME}"
if [ -f "$REDIS_TASKIQ_PASSWORD_SECRET" ]; then
  redis_taskiq_password="$(cat "$REDIS_TASKIQ_PASSWORD_SECRET")"
  TASKIQ_BROKER_URL="${TASKIQ_BROKER_URL}:${redis_taskiq_password}"
else
  warn NOT PASSWORD FOR REDIS USER
fi

TASKIQ_BROKER_URL="${TASKIQ_BROKER_URL}@${REDIS_TASKIQ_HOST}:${REDIS_TASKIQ_PORT}"
TASKIQ_BROKER_URL="${TASKIQ_BROKER_URL}/${REDIS_TASKIQ_DB}"

export REDIS_PASSWORD MONGO_PASSWORD TASKIQ_BROKER_URL KEYCLOAK_CLIENT_SECRET

if [ "$DEV_MODE" = 1 ]; then
    uv --no-progress pip install --system --editable .[reload]
    uv --no-progress pip install --system --editable "${SALTBOX_BRIDGE_MESSAGES_SRC_PATH}"
    uv --no-progress pip install --system --editable "${SALTBOX_SDK_SRC_PATH}"
fi

cmd_uvicorn() {
  cmd='/usr/bin/uvicorn saltbox_core.main:app'
  cmd="${cmd} --host=0.0.0.0 --port=8000"
  cmd="${cmd} --timeout-graceful-shutdown=${TIMEOUT_GRACEFUL_SHUTDOWN}"
  if [ "$DEV_MODE" = 1 ]; then
    cmd="$cmd --reload"
  fi
}

cmd_taskiq_worker() {
  # -fsd - autodiscover tasks in all modules
  # -tp - file pattern for autodiscover (default: **/tasks.py)
  # -r - autoreload for dev
  # -w - number of workers
  # --max-fails - max number of failed tasks before stopping the worker
  cmd='/usr/bin/taskiq worker saltbox_core.tkq:broker'
#  cmd="${cmd} saltbox_core.jobs saltbox_core.settings saltbox_core.salt -w 1 --max-fails 1"
  cmd="${cmd} -fsd -tp **/tiq_tasks.py -w 1 --max-fails 1"
  if [ "$DEV_MODE" = 1 ]; then
    cmd="$cmd --reload"
  fi
}

cmd_taskiq_scheduler() {
  # -fsd - autodiscover tasks in all modules
  # -fp - file pattern for autodiscover (default: **/tasks.py)
  # --skip-first-run - scheduler will wait until the start of the next minute and then start executing tasks
  # cmd="taskiq scheduler -tp **/tasksq.py saltbox_core.tkq_sched:scheduler saltbox_core.async_tasks" # bad
  # cmd="taskiq scheduler -tp **/tasksq.py saltbox_core.tkq_sched:scheduler saltbox_core.async_tasks.tasksq" # good

  cmd="/usr/bin/taskiq scheduler saltbox_core.tkq_sched:scheduler -fsd -tp **/tiq_tasks.py"
}

cmd_shell() {
  shift
  cmd="$*"
}

wrong_cmd() {
  warn "Unknown command \"${*}\""
  err "Try \"shell ${*}\" for arbitrary command"
}

case $1 in
  uvicorn) cmd_uvicorn ;;
  taskiq-worker) cmd_taskiq_worker ;;
  taskiq-scheduler) cmd_taskiq_scheduler ;;
  shell) cmd_shell "$@" ;;
  *) wrong_cmd "$@" ;;
esac

echo "$ ${cmd}"
exec $cmd
