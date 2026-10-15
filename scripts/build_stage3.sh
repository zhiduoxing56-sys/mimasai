#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
scripts/cxx.sh -std=c++17 -O2 -Ideps/SEAL-4.1.0/native/src -Ibuild/seal/native/src src/he_bridge.cpp build/seal/lib/libseal-4.1.a -pthread -o build/he_bridge
python3 - <<'PY'
import hashlib,json
from pathlib import Path
sha=lambda path:hashlib.sha256(Path(path).read_bytes()).hexdigest()
Path('build/he_bridge-build.json').write_text(json.dumps(dict(source_sha256=sha('src/he_bridge.cpp'),script_sha256=sha('scripts/build_stage3.sh'),binary_sha256=sha('build/he_bridge')),indent=2)+'\n')
PY
