#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
mkdir -p results/trained-he
/usr/bin/python3 scripts/unpack_deps.py > results/trained-he/dependency-restore.log
sh scripts/build_he.sh > results/trained-he/seal-build.log
sh scripts/build_stage3.sh > results/trained-he/bridge-build.log
/usr/bin/python3 verification/stage1.py > results/trained-he/stage1.log
/usr/bin/python3 verification/trained_he_chain.py --faults
