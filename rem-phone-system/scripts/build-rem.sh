#!/bin/bash
set -eo pipefail
cd "${REM_ANDROID_TREE:-/home/rembuild/android/lineage}"
export LC_ALL=C
export LANG=C
export TMPDIR="${REM_BUILD_TMP:-/home/rembuild/tmp}"
export OUT_DIR=out
export GOMAXPROCS=4
export NINJA_STATUS='[%f/%t %p] '
target="${REM_BUILD_TARGET:-bacon}"
case "$target" in
    bacon) ;;
    RemBody)
        # A component update uses the installed base build's timestamp. Avoid
        # regenerating the Android framework solely due to a new build date.
        export BUILD_DATETIME="$(cat out/build_date.txt)"
        [[ "$BUILD_DATETIME" =~ ^[0-9]+$ ]] || exit 1
        ;;
    *) echo 'Unsupported build target' >&2; exit 1 ;;
esac
mkdir -p "$TMPDIR"
source build/envsetup.sh
lunch rem_lavender-userdebug
m -j"${REM_BUILD_JOBS:-4}" "$target"
