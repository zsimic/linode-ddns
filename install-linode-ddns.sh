#!/bin/bash

[ -z "$TARGET" ] && TARGET=/config/scripts/linode-ddns
FOLDER=$(dirname $TARGET)
[ ! -d $FOLDER ] && echo "Folder $FOLDER does not exist" && exit 1

set -e

sudo curl -s -o$TARGET https://raw.githubusercontent.com/zsimic/linode-ddns/main/linode-ddns.py
sudo chmod 0755 $TARGET

sudo $TARGET -i _ask_ --commit

echo
cat << EOT
Now run this:

configure
set system task-scheduler task linode-ddns interval 30m
set system task-scheduler task linode-ddns executable path $TARGET
commit
save
EOT
