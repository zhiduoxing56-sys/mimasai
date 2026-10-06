"""Independent existing-model verification after cleanup; no backend rerun."""
import json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from verification.application import published_reference,verify_queries
from src.mpc import ROOT

def main():
 eid='a49152b33097752eaf81a7cba6d910a3';report,data,pub,prob=published_reference(eid);queries=verify_queries(eid,prob,False)
 result=dict(status='PASS_RETAINED_MODEL_CHECKPOINT_AND_QUERY_EVIDENCE',experiment=eid,queries=len(queries),checkpoint_iteration=report['checkpoint']['iteration'],checkpoint_to_f12_to_f7_verified=True,final_queries_match_same_model_reference=True,backend_reexecuted=False,materials_generated=False,full_recovery_role='independent verifier only',historical_acceptance_overwritten=False)
 (ROOT/'results/storage/retained-query-checks.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
