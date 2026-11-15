#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python -m unittest discover -s rem-cloud/tests -v
python -m unittest discover -s rem-phone-system/tests -v
python -m unittest discover -s rem-voice/service -p 'test_*.py' -v
node rem-phone-system/tests/visual-follow-test.mjs
classes=$(mktemp -d)
trap 'rm -rf -- "$classes"' EXIT
javac -encoding UTF-8 -d "$classes" \
  rem-phone-system/vendor/rem/RemBody/src/com/rem/body/BodyState.java \
  rem-phone-system/vendor/rem/RemBody/src/com/rem/body/vision/ObservationPolicy.java \
  rem-phone-system/tests/BodyStateTest.java \
  rem-phone-system/tests/ObservationPolicyTest.java
java -cp "$classes" BodyStateTest
java -cp "$classes" ObservationPolicyTest
python scripts/check-public-tree.py
