#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
export LD_LIBRARY_PATH="$PWD/deps/toolchain/usr/lib/x86_64-linux-gnu${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
mkdir -p build results/materials
# Transitive shared libraries are resolved by the runtime loader. No crypto checks
# are changed; this program only extracts PDF text using local Chinese CMaps.
scripts/cxx.sh -std=c++17 -Ideps/toolchain/usr/include/poppler scripts/pdf_text.cpp \
  -Ldeps/toolchain/usr/lib/x86_64-linux-gnu -Wl,--allow-shlib-undefined \
  -Wl,-rpath,"$PWD/deps/toolchain/usr/lib/x86_64-linux-gnu" -lpoppler -o build/pdf_text
build/pdf_text "$PWD/deps/toolchain/usr/share/poppler" \
  '参考资料/CACRcomp-latex-reference-style-v8 (1).pdf' \
  results/materials/competition-readable.txt 2>results/materials/pdf-warnings.log
