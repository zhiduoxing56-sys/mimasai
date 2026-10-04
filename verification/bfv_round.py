"""Independent exhaustive modular share rounding; actual two-process circuits."""
import json,secrets,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from verification.stage2 import session,launch,ROOT
from src.he_secure import round_cost
OUT=ROOT/'results/security-round';OUT.mkdir(parents=True,exist_ok=True)
def run(bits,q,pairs):
 t=1<<bits;plain=[dict(type='bfv_round',count=len(pairs),ciphertext_modulus=str(q),x=[],expected=[])]
 d,sid,dealer=session(bits,plain)
 for role in (0,1):
  path=d/f'S{role}/input.json';doc=json.loads(path.read_text());doc['operations'][0]['q_share']=[pair[role] for pair in pairs];path.write_text(json.dumps(doc))
 attempt,m=launch(d,sid,bits,timeout=180);assert all(v['success'] for v in m),m
 outputs=[json.loads((d/f'S{r}/output-{attempt}.json').read_text())['shares'][0] for r in (0,1)]
 expected=[(t*((a+b)%q)+q//2)//q%t for a,b in pairs];assert [(a+b)%t for a,b in zip(*outputs)]==expected
 assert all(v['preprocessing']['consumed']==dealer['generated'] for v in m)
 return dict(bits=bits,modulus_bits=q.bit_length(),count=len(pairs),session=sid,wire_bytes=sum(v['communication']['bytes_sent'] for v in m),rounds=m[0]['communication']['exchange_rounds'],materials=dealer['generated'],seconds=max(sum(o['elapsed_seconds'] for o in v['operations']) for v in m))
def main():
 runs=[run(bits,q,[(a,b) for a in range(q) for b in range(q)]) for bits,q in [(2,5),(3,17),(4,37)]]
 qs=[36028797017571329,36028797018652673,18014398508138497];q=__import__('math').prod(qs);t=1<<32;values=[0,1,q-1,q//2,q//2+1]+[k*q//t+delta for k in [1,t//2,t-1] for delta in [-1,0,1]];pairs=[(a,b) for a in values for b in [0,1,q-1]]+[(secrets.randbelow(q),secrets.randbelow(q)) for _ in range(128)];runs.append(run(32,q,pairs))
 (OUT/'bfv-round.json').write_text(json.dumps(dict(status='PASS_EXACT_SECRET_BFV_ROUND',runs=runs),indent=2)+'\n');print(json.dumps(dict(status='PASS_EXACT_SECRET_BFV_ROUND',checks=sum(r['count'] for r in runs)),indent=2))
if __name__=='__main__':main()
