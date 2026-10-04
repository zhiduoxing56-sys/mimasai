#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
/usr/bin/python3 scripts/unpack_deps.py
sh scripts/build_he.sh
sh scripts/build_stage3.sh
exec /usr/bin/python3 scripts/run_application.py "$@"
