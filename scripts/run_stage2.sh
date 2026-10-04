#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
/usr/bin/python3 verification/stage2.py
