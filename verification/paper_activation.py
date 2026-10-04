"""Exhaust paper Eq. (1), literal Algorithm 1 and proposed correction.
DCF is a truth-table oracle only. This does not implement FSS keys.
"""
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.reference import corrected_activation
root=Path(__file__).resolve().parents[1]
config=json.loads((root/"config/phase0.json").read_text())
rows=[]
for n in config["activation_reference_bits"]:
    k=n-1
    full, narrow, half = 1<<n, 1<<k, 1<<(k-1)
    failure_paper=failure_competition=failure_range=None
    total=0
    for raw in range(full):
        z=raw if raw<full//2 else raw-full
        in_range=-half<=z<half
        for rz in range(full):
            public=(raw+rz)%full
            public_k=public%narrow
            y0=public_k%half
            neg_mask=(-rz)%narrow
            y1=neg_mask%half
            indicator=int(half-y0-1<y1)
            msb=public_k//half
            for rb in (0,1):
                rp=neg_mask//half ^ 1 ^ rb
                expected_narrow=int((raw%narrow)<half)^rb
                equation=msb ^ indicator ^ rp
                assert equation==expected_narrow
                for t0 in (0,1):
                    t1=t0^indicator
                    for rp0 in (0,1):
                        rp1=rp0^rp
                        paper=(msb^t0^rp0)^(msb^t1^rp0)
                        competition=(msb^t0^rp0)^(msb^t1^rp1)
                        fixed=(msb^t0^rp0)^(t1^rp1)
                        assert fixed==equation
                        if in_range:
                            reference=corrected_activation(z,n,k,rz,rb,t0,rp0)
                            assert reference['masked_sign_shares']==[msb^t0^rp0,t1^rp1]
                            assert reference['nonnegative']==int(z>=0)
                            assert reference['relu']==max(z,0)
                        else:
                            try: corrected_activation(z,n,k,rz,rb,t0,rp0)
                            except ValueError: pass
                            else: raise AssertionError('outside range accepted')
                        sample={"n":n,"k":k,"z":z,"rz":rz,"rb":rb,"public":public,
                                "public_msb":msb,"indicator":indicator,"rp0":rp0,"rp1":rp1,
                                "expected_masked_drelu":expected_narrow}
                        if in_range and paper!=expected_narrow and failure_paper is None:
                            failure_paper={**sample,"actual":paper}
                        if in_range and competition!=expected_narrow and failure_competition is None:
                            failure_competition={**sample,"actual":competition}
                if in_range:
                    assert (equation^rb)==int(z>=0)
                    # Paper MUX affine keys, using deterministic splits for algebra only.
                    # For each public masked bit h, alpha0+alpha1=h XOR rb;
                    # beta0+beta1=-(h XOR rb)*rz mod 2^n.
                    for h in (0,1):
                        b=h^rb
                        alpha0,alpha1=1,(b-1)%full
                        beta0,beta1=2,(-b*rz-2)%full
                        value=(alpha0*public+beta0+alpha1*public+beta1)%full
                        assert value==(b*raw)%full
                    assert ((equation^rb)*raw)%full==max(z,0)%full
                elif failure_range is None and (equation^rb)!=int(z>=0):
                    failure_range={"n":n,"k":k,"z":z,"rz":rz,"rb":rb,
                                   "narrow_drelu":equation^rb,"full_drelu":int(z>=0)}
                total+=1
    assert failure_paper is not None and failure_competition is not None and failure_range is not None
    rows.append({"n":n,"k":k,"input_mask_bit_cases":total,"paper_algorithm_failure":failure_paper,
                 "competition_algorithm_failure":failure_competition,"outside_range_failure":failure_range,
                 "equation_and_proposed_correction":"PASS","affine_mux":"PASS"})
output={"status":"ORIGINAL_ALGORITHMS_FAIL_CORRECTION_REFERENCE_PASSES","cases":rows,
        "scope":"No DCF/FSS key implementation or protocol security validation"}
(root/"results/paper-activation.json").write_text(json.dumps(output,indent=2)+"\n")
print(json.dumps(output,indent=2))
