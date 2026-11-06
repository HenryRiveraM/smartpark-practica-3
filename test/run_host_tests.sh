#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
build_dir=$(mktemp -d "${TMPDIR:-/tmp}/smartpark-tests.XXXXXX")
trap 'rm -rf "$build_dir"' EXIT HUP INT TERM
"${CXX:-c++}" -std=c++17 -Wall -Wextra -Werror -pedantic \
    -Itest/host/fakes -Iinclude test/host/test_main.cpp \
    src/UltrasonicSensor.cpp src/BarrierServo.cpp src/main.cpp -o "$build_dir/tests"
"$build_dir/tests"
