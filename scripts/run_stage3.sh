#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
sh scripts/build_stage3.sh
/usr/bin/python3 verification/stage3.py "$@"
if [ "$#" -eq 0 ]; then
    /usr/bin/python3 verification/stage3_faults.py
    /usr/bin/python3 scripts/report_stage3.py
fi
