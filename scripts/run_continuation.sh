#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
mkdir -p results/continuation
# Existing stage-zero dependencies and stage-one fixtures are prerequisites.
test -f results/stage1/quantized-inputs.json
test -f results/stage3/costs.json
if [ ! -x build/he_bridge ]; then sh scripts/build_stage3.sh; fi
/usr/bin/python3 verification/two_layer_he.py > results/continuation/two-layer-he.log 2>&1
/usr/bin/python3 verification/operators.py > results/continuation/operators.log 2>&1
/usr/bin/python3 verification/training.py > results/continuation/training.log 2>&1
/usr/bin/python3 verification/training.py --indexed > results/continuation/training-indexed.log 2>&1
/usr/bin/python3 verification/publication.py > results/continuation/publication.log 2>&1
/usr/bin/python3 verification/publication.py --indexed > results/continuation/publication-indexed.log 2>&1
/usr/bin/python3 verification/continuation_checks.py > results/continuation/targeted-checks.log 2>&1
/usr/bin/python3 verification/stage2.py > results/continuation/stage2-regression.log 2>&1
/usr/bin/python3 verification/stage2_round2.py > results/continuation/stage2-round2-regression.log 2>&1
/usr/bin/python3 scripts/report_continuation.py
