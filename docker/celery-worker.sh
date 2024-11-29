#! /bin/sh
set -e

err() {
  2>&1 echo "$1" && exit 1
}

application=fastms_core.celery
concurrency=4

case $1 in
  tasks) queue='tasks' && shift ;;
  -c|--concurrency) concurrency="$2" && shift 2 ;;
  *) echo "unknown arg \"$1\"" && exit 1 ;;
esac

if [ -z "$queue" ]; then err 'Missing QUEUE arg' && exit 1; fi

. export-secrets.sh

cmd="celery --app='${application}' worker"
cmd="${cmd} --concurrency=${concurrency} --pool=gevent --queues=${queue}"

echo "$ ${cmd}"
eval "$cmd"
