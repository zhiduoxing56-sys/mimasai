"""Offline-only restore from downloaded packages, after verifying recorded hashes."""
import hashlib
import json
import subprocess
import tarfile
import zipfile
from pathlib import Path
root=Path(__file__).resolve().parents[1]
lock=json.loads((root/"config/dependencies.lock.json").read_text())
required=[row for row in lock if row["file"].endswith(".deb") or row["file"]=="SEAL-4.1.0.tar.gz"]
missing=[row["file"] for row in required if not (root/"deps/downloads"/row["file"]).exists()]
if missing: raise SystemExit("missing offline runtime archives: " + ", ".join(missing))
for row in required:
    file=root/"deps/downloads"/row["file"]
    if not file.exists():
        raise SystemExit(f"missing local dependency: {file}")
    if hashlib.sha256(file.read_bytes()).hexdigest()!=row["sha256"]:
        raise SystemExit(f"dependency hash mismatch: {file}")
tc=root/"deps/toolchain"
tc.mkdir(parents=True,exist_ok=True)
for file in sorted(root/"deps/downloads"/row["file"] for row in required if row["file"].endswith(".deb")):
    subprocess.run(["/usr/bin/dpkg-deb","-x",str(file),str(tc)],check=True)
if not (tc/"lib").exists(): (tc/"lib").symlink_to("usr/lib")
(tc/"lib64").mkdir(exist_ok=True)
link=tc/"lib64/ld-linux-x86-64.so.2"
if not link.exists(): link.symlink_to("../usr/lib/x86_64-linux-gnu/ld-linux-x86-64.so.2")
with tarfile.open(root/"deps/downloads/SEAL-4.1.0.tar.gz") as tar:
    tar.extractall(root/"deps",filter="data")
print("Verified and unpacked locked runtime archives; no system installation. Optional PDF/Python analysis dependencies were not restored.")
