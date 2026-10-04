#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
root=$PWD
/usr/bin/python3 verification/reference.py > results/reference-run.log
export LD_LIBRARY_PATH="$root/deps/toolchain/usr/lib/x86_64-linux-gnu${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
cmake="$root/deps/toolchain/usr/bin/cmake"
"$cmake" -S deps/SEAL-4.1.0 -B build/seal \
  -DCMAKE_C_COMPILER="$root/scripts/cc.sh" -DCMAKE_CXX_COMPILER="$root/scripts/cxx.sh" \
  -DCMAKE_MAKE_PROGRAM="$root/deps/toolchain/usr/bin/make" \
  -DCMAKE_AR="$root/deps/toolchain/usr/bin/x86_64-linux-gnu-ar" \
  -DCMAKE_RANLIB="$root/deps/toolchain/usr/bin/x86_64-linux-gnu-ranlib" \
  -DCMAKE_BUILD_TYPE=Release -DSEAL_BUILD_DEPS=OFF -DSEAL_USE_MSGSL=OFF \
  -DSEAL_USE_ZLIB=OFF -DSEAL_USE_ZSTD=OFF -DSEAL_BUILD_EXAMPLES=OFF -DSEAL_BUILD_TESTS=OFF
"$cmake" --build build/seal -j 2
scripts/cxx.sh -std=c++17 -O2 -Ideps/SEAL-4.1.0/native/src -Ibuild/seal/native/src \
  verification/seal_probe.cpp build/seal/lib/libseal-4.1.a -pthread -o build/seal_probe
/usr/bin/python3 scripts/run_he.py
