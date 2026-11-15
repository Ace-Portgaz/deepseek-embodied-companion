#!/usr/bin/env bash
set -euo pipefail
source /etc/os-release
[[ "${ID:-}" == ubuntu && "${VERSION_ID:-}" == 22.04 ]]
printf 'OS: %s\n' "$PRETTY_NAME"
printf 'Architecture: '; uname -m
printf 'Build volume: '; findmnt -no FSTYPE --target /home/rembuild/android
printf 'Free storage:\n'; df -h /home/rembuild/android
printf 'Memory:\n'; free -h
printf 'Java:\n'; java -version
printf 'Repo:\n'
if [[ -d /home/rembuild/android/lineage/.repo/repo ]]; then
  (cd /home/rembuild/android/lineage && /home/rembuild/bin/repo version)
else
  /home/rembuild/bin/repo --version
fi
printf 'User:\n'; id rembuild
printf 'Source tree complete: no (separate verification required)\n'
