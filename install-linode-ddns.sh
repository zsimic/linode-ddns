#!/bin/bash

[ -z "$TARGET" ] && TARGET=/config/scripts/linode-ddns
FOLDER=$(dirname $TARGET)
[ ! -d $FOLDER ] && echo "Folder $FOLDER does not exist" && exit 1

set -e

curl -s -o$TARGET https://raw.githubusercontent.com/zsimic/linode-ddns/main/linode-ddns.py
chmod 0755 $TARGET

ACTION=$1
if [[ "$ACTION" == "clean" ]]; then
  rm ~/.ssh/linode-ddns.json
elif [[ "$ACTION" == "get" ]]; then
  exit 0
elif [[ -n "$ACTION" ]]; then
  echo "Unknown action '$ACTION'"
  exit 1
fi

$TARGET -i _ask_ --commit

echo
cat << EOT
To schedule this in EdgeRouter:

configure
set system task-scheduler task linode-ddns interval 30m
set system task-scheduler task linode-ddns executable path $TARGET
commit
save
EOT
