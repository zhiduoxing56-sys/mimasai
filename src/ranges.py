"""Single-source public real bounds, exact fixed-unit intervals and bit widths."""
from .mpc import settings,require

def operand(name,fraction):
    real=settings()['range_policy']['operand_bounds_real'][name]
    value=real*(1<<fraction);radius=round(value)
    require(radius==value and radius>0,'BOUND_QUANTIZATION')
    bits=(radius-1).bit_length()+1
    return bits if radius & (radius-1)==0 else dict(bits=bits,radius=radius)

def bit_width(bound):return bound['bits'] if isinstance(bound,dict) else bound

def radius(bound):
    if isinstance(bound,dict):
        require(set(bound)=={'bits','radius'} and type(bound['radius'])==int and bound['radius']>0 and bound['radius'] & (bound['radius']-1)!=0 and type(bound['bits'])==int and bound['bits']==(bound['radius']-1).bit_length()+1,'BOUND_DESCRIPTOR')
        return bound['radius']
    require(type(bound)==int and 1<=bound<=32,'BOUND_DESCRIPTOR')
    return 1<<(bound-1)

def check_interval(e,values,bound):
    from .operators import public,compare_boolean,assert_batch
    magnitude=radius(bound);require(bit_width(bound)<=e.bits and len(values)>0,'RANGE_ARGUMENT')
    valid=compare_boolean(e,values+public(e,magnitude-1,len(values)),public(e,-magnitude,len(values))+values)
    assert_batch(e,valid,'RANGE_REJECTED')
