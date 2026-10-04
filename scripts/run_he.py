"""Run native probes with the one central parameter file; preserve failures."""
import json
import subprocess
from pathlib import Path
root = Path(__file__).resolve().parents[1]
config = json.loads((root/"config/phase0.json").read_text())
records = []
fixture=json.loads((root/"results/reference.json").read_text())["graph_polynomial"]
inputs=[*fixture["quantized_weights"][0][:2],*fixture["quantized_features"][:2]]
for degree in config["he_degrees"]:
    proc = subprocess.run([str(root/"build/seal_probe"), str(degree), str(config["ring_bits"]),
                           str(config["fraction_bits"]), *map(str,config["he_coefficient_bits"]),*map(str,inputs)],
                          text=True, capture_output=True, cwd=root)
    record = {"degree": degree, "exit_code": proc.returncode, "stdout": proc.stdout,
              "stderr": proc.stderr, "checks": [json.loads(line) for line in proc.stdout.splitlines()]}
    for check in record["checks"]:
        if check.get("stage")=="sample_extraction":
            moduli=check["moduli"]
            q=1
            for modulus in moduli: q*=modulus
            phase=sum(r*(q//m)*pow(q//m,-1,m) for r,m in zip(check["phase_residues"],moduli))%q
            decoded=((phase*check["plain_modulus"]+q//2)//q)%check["plain_modulus"]
            check["decoded_plaintext"]=decoded
            check["passed"]=decoded==check["expected_plaintext"]
            if not check["passed"]: record["exit_code"]=1
    records.append(record)
    print(json.dumps(record))
(root/"results/he.json").write_text(json.dumps(records, indent=2)+"\n")
if not any(r["exit_code"] == 0 for r in records):
    raise SystemExit(1)
