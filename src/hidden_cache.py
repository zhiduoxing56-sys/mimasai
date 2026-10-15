"""Role-local, model/input-bound first-layer shares for later fresh requests."""
import hashlib
import json
from pathlib import Path
from .mpc import private_write, require


def digest(path):
    hasher=hashlib.sha256()
    with Path(path).open('rb') as source:
        for block in iter(lambda:source.read(1024*1024),b''):hasher.update(block)
    return hasher.hexdigest()


def sources(own,model):
    own=Path(own);layer=own/'he-layer0'
    manifest=json.loads((layer/'he.json').read_text())
    files={'input-shares.json':own/'input-shares.json',
           'model':own/('model-'+model['model_id']+'.json'),
           'he.json':layer/'he.json'}
    require(all(path.is_file() and not path.is_symlink() for path in files.values()),'HIDDEN_SOURCE_MISSING')
    for name,expected in manifest['local_integrity'].items():
        path=layer/name
        require(path.is_file() and not path.is_symlink() and path.resolve().is_relative_to(layer.resolve()) and digest(path)==expected,'HIDDEN_HE_ASSET_CHANGED')
    return {name:digest(path) for name,path in files.items()}


def capture(own,role,session,attempt,op,output):
    require(op['type']=='he_aggregate' and op['model_layer']==0 and op['activation']=='fss','HIDDEN_CAPTURE_PLAN')
    count=op['count'];require(len(output)==3*count,'HIDDEN_CAPTURE_SHAPE')
    payload=dict(role=role,source_session=session,binding=op['cache_binding'],model_id=op['model']['model_id'],
                 asset_hashes=sources(own,op['model']),shares=output[-count:])
    private_write(Path(own)/('first-layer-'+attempt+'.json'),payload)


def load(own,role,op,mod):
    require(op['type']=='load_hidden' and op['count']>0,'HIDDEN_LOAD_PLAN')
    payload=json.loads((Path(own)/'hidden-state.json').read_text())
    require(payload['role']==role and payload['source_session']==op['source_session'] and
            payload['binding']==op['cache_binding'] and payload['model_id']==op['model']['model_id'],'HIDDEN_CACHE_BINDING')
    require(payload['asset_hashes']==sources(own,op['model']),'HIDDEN_SOURCE_CHANGED')
    values=payload['shares'];require(len(values)==op['count'] and all(type(v)==int and 0<=v<mod for v in values),'HIDDEN_CACHE_SHAPE')
    return values
