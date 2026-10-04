"""Persistent per-role model publication. No complete-parameter recovery API."""
import json
from pathlib import Path
from .mpc import VERSION,private_write,require,settings

def binding(model_id,node_order,features,hidden,classes,fraction):
 c=settings()
 return dict(model_id=model_id,model_version=c['model_reference']['version'],node_order=node_order,dimensions=[features,hidden,classes],ring_bits=c['ring_bits'],fraction_bits=fraction,bias=c['model_reference']['bias'],activations=c['model_reference']['activations'],query=c['model_reference']['query'],truncation='signed_floor_after_each_matrix_dot',order=c['model_reference']['inference_order'],probability_algorithm='bounded_T2_power_then_exact_positive_division',probability_fraction_bits=c['probability_fraction_bits'],approximation=c['approximation'],range_policy=c['range_policy'])
def validate(doc):
 c=settings();require(isinstance(doc.get('model_id'),str) and len(doc['model_id'])==32 and all(v in '0123456789abcdef' for v in doc['model_id']),'MODEL_IDENTIFIER')
 require(isinstance(doc.get('dimensions'),list) and len(doc['dimensions'])==3 and all(type(v)==int and v>0 for v in doc['dimensions']),'MODEL_DIMENSIONS')
 require(set(doc)==set(binding(doc['model_id'],doc['node_order'],*doc['dimensions'],doc['fraction_bits'])),'MODEL_FIELDS')
 require(doc==binding(doc['model_id'],doc['node_order'],*doc['dimensions'],doc['fraction_bits']),'MODEL_CONFIG_BINDING')
 require(len(doc['model_id'])==32 and len(set(doc['node_order']))==len(doc['node_order']),'MODEL_IDENTIFIER')
 require(doc['ring_bits']==32 and 0<doc['fraction_bits']<doc['ring_bits'] and doc['bias']=='public_fixed_zero','MODEL_NUMERICS')
def publish(e,own,weights,op):
 from .operators import public
 model=op['model'];validate(model);f=model['fraction_bits'];source=op['source_fraction'];count=op['count']
 require(len(weights)==count and count==model['dimensions'][0]*model['dimensions'][1]+model['dimensions'][1]*model['dimensions'][2],'MODEL_SHAPE')
 require(source>=f,'UNVERIFIED_PRECISION_INCREASE');e.check_range(weights,source+3)
 converted=e.truncate(weights,source-f) if source>f else weights[:];e.check_range(converted,f+3)
 random,span=e.materials.take('refresh',count);peer=e.channel.exchange(e.op,'model_refresh_randomness',[count],random,span=span)
 refreshed=[(v+a-b)%e.mod for v,a,b in zip(converted,random,peer)]
 path=Path(own)/('model-'+model['model_id']+'.json');private_write(path,dict(version='additive-model-v1',role=e.role,binding=model,shares=refreshed))
 return load(e.role,path,model)
def load(role,path,expected):
 data=json.loads(Path(path).read_text());validate(expected);require(data['version']=='additive-model-v1' and data['role']==role and data['binding']==expected,'MODEL_LOAD_BINDING')
 f,h,c=expected['dimensions'];require(len(data['shares'])==f*h+h*c and all(type(v)==int and 0<=v<1<<32 for v in data['shares']),'MODEL_LOAD_SHARES')
 return data['shares']
