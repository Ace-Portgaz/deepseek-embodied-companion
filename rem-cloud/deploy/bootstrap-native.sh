#!/bin/bash
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
apt-get -o DPkg::Lock::Timeout=120 install -y python3-venv python3-pip ffmpeg libopus0
if ! id rem >/dev/null 2>&1; then
    useradd --system --home-dir /var/lib/rem-cloud --create-home --shell /usr/sbin/nologin rem
fi
install -d -m 0755 /opt/rem-cloud
install -d -m 0700 -o rem -g rem /var/lib/rem-cloud
python3 -m venv /opt/rem-cloud/venv
PIP_CONFIG_FILE=/dev/null /opt/rem-cloud/venv/bin/python -m pip install --disable-pip-version-check \
  --index-url https://pypi.org/simple --no-cache-dir -r /opt/rem-cloud/deploy/requirements-cloud.txt
