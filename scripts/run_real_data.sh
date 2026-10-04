#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
mkdir -p results/real-data
/usr/bin/python3 scripts/unpack_deps.py > results/real-data/dependency-restore.log
sh scripts/build_he.sh > results/real-data/seal-build.log
sh scripts/build_stage3.sh > results/real-data/bridge-build.log
/usr/bin/python3 verification/range_budget.py
/usr/bin/python3 verification/scale_budget.py > results/real-data/scale-budget.log
/usr/bin/python3 verification/cora_full_reference.py --download
steps=$(/usr/bin/python3 -c 'from src.reference import config; print(config()["data_experiment"]["secure_iteration_budget"])')
/usr/bin/python3 verification/real_data.py --download --secure-steps "${1:-$steps}"
/usr/bin/python3 verification/real_chain.py --faults
