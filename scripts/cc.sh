#!/bin/sh
set -eu
root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
tc="$root/deps/toolchain"
export LD_LIBRARY_PATH="$tc/usr/lib/x86_64-linux-gnu${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
exec "$tc/usr/bin/x86_64-linux-gnu-gcc-13" --sysroot="$tc" -B"$tc/usr/bin/" -B"$tc/usr/lib/gcc/x86_64-linux-gnu/13/" -B"$tc/usr/lib/x86_64-linux-gnu/" "$@"
