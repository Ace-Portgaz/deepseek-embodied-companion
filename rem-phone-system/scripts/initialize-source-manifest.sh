#!/usr/bin/env bash
# Bootstrap the repo tool and manifest only. No `repo sync` or device operation.
set -euo pipefail
[[ "$(id -un)" == rembuild ]] || { echo 'Run as the dedicated rembuild user.' >&2; exit 1; }
workspace=/home/rembuild/android/lineage
mkdir -p "$workspace"
cd "$workspace"
if [[ -e .repo/manifest.xml ]]; then
  echo 'Existing source manifest preserved; review it before reinitializing.'
  exit 0
fi
git config --global user.name 'Rem Build'
git config --global user.email 'rem-build@localhost'
/home/rembuild/bin/repo init -u https://github.com/LineageOS/android.git -b lineage-18.1 \
  --git-lfs --no-clone-bundle --depth=1
git -C .repo/manifests rev-parse HEAD
printf '\nManifest initialized only; full source sync has NOT started.\n'
