#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
scripts/cxx.sh -std=c++17 -O2 -Ideps/SEAL-4.1.0/native/src -Ibuild/seal/native/src src/he_bridge.cpp build/seal/lib/libseal-4.1.a -pthread -o build/he_bridge
