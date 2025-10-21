#! /bin/bash

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

declare -r tiq_tasks_pattern='saltbox_core/**/tiq_tasks.py'
workdir="$PWD"

cmd_uvicorn() {
  cmd=(/usr/bin/uvicorn saltbox_core.main:app --host=0.0.0.0 --port=8000)
  cmd+=(--timeout-graceful-shutdown="${TIMEOUT_GRACEFUL_SHUTDOWN}")
  if [ "$DEV_MODE" = 1 ]; then
    cmd+=(--reload)
  fi
}

cmd_taskiq_worker() {
  cmd=(/usr/bin/taskiq worker saltbox_core.tkq:broker --fs-discover)
  cmd+=("--tasks-pattern=${tiq_tasks_pattern}" --workers=1 --max-fails=1)
  if [ "$DEV_MODE" = 1 ]; then
    cmd+=(--reload)
    workdir='/mnt/saltbox-core/'
  else
    workdir='/usr/lib/python3/site-packages/'
  fi
}

cmd_taskiq_scheduler() {
  cmd=(/usr/bin/taskiq scheduler saltbox_core.tkq_sched:scheduler)
  cmd+=(--fs-discover "--tasks-pattern=${tiq_tasks_pattern}")
  if [ "$DEV_MODE" != 1 ]; then
    workdir='/usr/lib/python3/site-packages/'
  fi
}

cmd_shell() {
  cmd=("${@:2}")
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

cd "$workdir"
echo "Current working directory is '$PWD'"
echo "$ ${cmd[*]}"
exec "${cmd[@]}"
