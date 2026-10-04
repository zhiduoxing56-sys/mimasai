#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
/usr/bin/python3 verification/stage1.py
/usr/bin/python3 verification/reference.py
/usr/bin/python3 verification/paper_activation.py
