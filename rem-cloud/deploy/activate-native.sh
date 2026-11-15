#!/bin/bash
set -euo pipefail
install -d -m 0700 -o rem -g rem /var/lib/rem-cloud/data
server=/opt/rem-cloud/build/server
install -d -m 0755 "$server/config/assets/wakeup_words"
if [ ! -L "$server/data" ]; then
    if [ -e "$server/data" ]; then mv "$server/data" "$server/data-packaged"; fi
    ln -s /var/lib/rem-cloud/data "$server/data"
fi
if [ ! -L "$server/tmp" ]; then
    if [ -e "$server/tmp" ]; then mv "$server/tmp" "$server/tmp-packaged"; fi
    ln -s /run/rem-cloud "$server/tmp"
fi
install -m 0644 /opt/rem-cloud/deploy/rem-cloud.service /etc/systemd/system/rem-cloud.service
systemctl daemon-reload
systemctl enable --now rem-cloud.service
systemctl is-active rem-cloud.service
