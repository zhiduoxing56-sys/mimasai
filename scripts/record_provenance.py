import hashlib
import json
import subprocess
import sys
from pathlib import Path
root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root/"deps/python"))
from pypdf import PdfReader
rows=[]
for file in sorted((root/"deps/downloads").iterdir()):
    if not file.is_file(): continue
    rows.append({"file":file.name,"sha256":hashlib.sha256(file.read_bytes()).hexdigest(),
                 "package":subprocess.check_output(["dpkg-deb","-f",str(file),"Package","Version"],text=True) if file.suffix==".deb" else None})
(root/"results/dependency-inventory.json").write_text(json.dumps(rows,indent=2)+"\n")
manifest=[]
base=Path("/mnt/e/WSL/GNN-Project/参考材料")
for file in sorted((root/"参考资料").glob("*.pdf")):
    source=base/file.name
    manifest.append({"file":file.name,"source":str(source),
                     "pdf_pages":len(PdfReader(file).pages),
                     "sha256":hashlib.sha256(file.read_bytes()).hexdigest(),
                     "source_same":file.read_bytes()==source.read_bytes()})
(root/"results/material-manifest.json").write_text(json.dumps(manifest,indent=2,ensure_ascii=False)+"\n")
tree=json.loads((root/"results/secgnn_tree.json").read_text())
audit=[]
for name in ["mpcUtil.cpp","typedef.h","README.md"]:
    content=(root/"deps/downloads"/("secgnn-"+name)).read_bytes()
    blob=hashlib.sha1(b"blob "+str(len(content)).encode()+b"\0"+content).hexdigest()
    expected=next(item["sha"] for item in tree["tree"] if item["path"]==name)
    audit.append({"path":name,"blob_sha1":blob,"tree_blob":expected,"matches":blob==expected})
(root/"results/secgnn-source-audit.json").write_text(json.dumps({"commit":tree["sha"],"files":audit},indent=2)+"\n")
