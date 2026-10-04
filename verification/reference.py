"""Independent arithmetic oracle; no secure protocol is implemented here."""
import json
import math
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.reference import graph,config

ROOT = Path(__file__).resolve().parents[1]
C = config()
T = 1 << C["ring_bits"]
S = 1 << C["fraction_bits"]

def multiply(a, b):
    n = len(a)
    out = [0] * n
    for i, x in enumerate(a):
        for j, y in enumerate(b):
            k = i + j
            out[k % n] = (out[k % n] + (1 if k < n else -1) * x * y) % T
    return out

def encode_negative(weights, n):
    out = [0] * n
    out[0] = weights[0] % T
    for j, w in enumerate(weights[1:], 1):
        out[n-j] = -w % T  # x^-j = -x^(N-j) in x^N+1
    return out

def graph_check():
    g = C["graph_reference"]
    m, n = g["nodes"], C["polynomial_degree_reference"]
    a,degrees,p = graph(g)
    q = [[round(w*S) for w in row] for row in p]
    x = [round(row[0]*S) for row in g["features"]]
    assert m <= n
    columns = [[round(row[k]*S) for row in g["features"]] for k in range(len(g["features"][0]))]
    rows = []
    for i in range(m):
        neighbors = [(j, q[i][j]) for j in range(m) if a[i][j]]
        padded = neighbors + [(0, 0)] * (max(sum(bool(v) for v in row) for row in a)-len(neighbors))
        direct = sum(w*x[j] for j, w in neighbors)
        assert direct == sum(w*x[j] for j, w in padded)
        const = multiply(encode_negative(q[i], n), x + [0]*(n-m))[0]
        assert const == direct % T
        for column in columns:
            direct_column=sum(w*column[j] for j,w in neighbors)
            assert direct_column==sum(w*column[j] for j,w in padded)
            assert multiply(encode_negative(q[i],n),column+[0]*(n-m))[0]==direct_column%T
        rows.append({"node": i, "constant_ring": const, "signed_raw_scale_S2": direct,
                     "rescaled_floor": direct//S, "real_reference": sum(p[i][j]*x[j]/S for j in range(m))})
    # Find and preserve a truncation counterexample with exact integer arithmetic.
    example = None
    for aa in range(1, S):
        for xx in range(1, S):
            ww = S+S//2
            aggregate_first = ((aa*xx)//S * ww)//S
            transform_first = (aa*((xx*ww)//S))//S
            if aggregate_first != transform_first:
                example = {"P": aa, "X": xx, "W": ww, "scale": S,
                           "aggregate_first": aggregate_first, "transform_first": transform_first}
                break
        if example:
            break
    assert example
    # A target needs full-graph degrees and a two-hop dependency closure.
    induced_weight = 1/math.sqrt(2*2)
    assert induced_weight != p[0][1]
    return {"status": "PASS_REFERENCE_ONLY", "degrees": degrees, "weights": p,
            "quantized_weights":q,"quantized_features":x,"feature_columns_checked":len(columns),
            "rows": rows, "truncation_counterexample": example,
            "subgraph_counterexample": {"edge": [0,1], "full_weight": p[0][1], "induced_weight": induced_weight}}

def activation_check():
    records = []
    for bits in C["activation_reference_bits"]:
        modulus = 1 << bits
        count = 0
        naive_failure = None
        shrink_failure = None
        for x in range(modulus):
            signed = x if x < modulus//2 else x-modulus
            expected_sign = int(signed < 0)
            for r in range(modulus):
                public = (x+r) % modulus
                carry = int(public < r)
                recovered = (public-r+carry*modulus) % modulus
                assert recovered == x
                # Exact unmasking oracle; not a distributed comparison protocol.
                sign = int(recovered >= modulus//2)
                assert sign == expected_sign
                assert (1-sign)*signed == max(signed, 0)
                if naive_failure is None and ((public>>(bits-1)) ^ (r>>(bits-1))) != sign:
                    naive_failure = {"x": signed, "mask": r, "public": public, "expected_sign": sign}
                small_mod = modulus//2
                small_x = x % small_mod
                small_sign = int(small_x >= small_mod//2)
                if -small_mod//2 <= signed < small_mod//2:
                    assert small_sign == sign
                elif shrink_failure is None and small_sign != sign:
                    shrink_failure = {"x": signed, "narrow_residue": small_x, "expected_sign": sign, "narrow_sign": small_sign}
                count += 1
        records.append({"bits": bits, "input_mask_pairs": count,
                        "naive_public_msb_xor_failure": naive_failure,
                        "out_of_range_shrink_failure": shrink_failure})
        selection_count = 0
        duplicate_public_failure = None
        for x in range(modulus):
            signed = x if x < modulus//2 else x-modulus
            b = int(signed < 0)
            for r in range(modulus):
                for s in range(modulus):
                    u, v = (x+r)%modulus, (b+s)%modulus
                    # Algebraic offline splits only, not cryptographic randomness.
                    r0, r1 = 1, (r-1)%modulus
                    s0, s1 = 2, (s-2)%modulus
                    k0, k1 = 3, (r*s-3)%modulus
                    public_term = (1-v)*u
                    c0 = public_term+(v-1)*r0+u*s0-k0
                    c1 = (v-1)*r1+u*s1-k1
                    assert (c0+c1)%modulus == max(signed, 0)%modulus
                    if duplicate_public_failure is None and (c0+c1+public_term)%modulus != max(signed,0)%modulus:
                        duplicate_public_failure = {"x": signed, "r": r, "s": s,
                                                   "public_term": public_term%modulus,
                                                   "wrong": (c0+c1+public_term)%modulus,
                                                   "expected": max(signed,0)%modulus}
                    selection_count += 1
        records[-1]["masked_selection_cases"] = selection_count
        records[-1]["duplicate_public_term_failure"] = duplicate_public_failure
    return {"status": "PASS_GENERIC_ORACLE_ONLY", "cases": records,
            "warning": "No claim about paper Algorithm 1, offline constants, key distribution or secure selection."}

if __name__ == "__main__":
    result = {"graph_polynomial": graph_check(), "activation": activation_check()}
    (ROOT/"results/reference.json").write_text(json.dumps(result, indent=2)+"\n")
    print(json.dumps(result, indent=2))
