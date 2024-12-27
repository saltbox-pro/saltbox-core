#! /bin/sh
# shellcheck source=./shell_init.sh
. /etc/shell_init.sh

[ -n "$1" ] && err "Unknown arg \"$1\""

cmd="python3 /mnt/salt_box_core/fastms_core/minions/consumer.py"

echo "$ ${cmd}"
eval "$cmd"
