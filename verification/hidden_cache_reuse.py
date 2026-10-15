"""Fresh-session role-local hidden-share reuse; no training or live assets."""
import copy,json,os,secrets,shutil,subprocess,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from verification.final_he_compare import ISOLATED_ROOT  # isolated gate, assets and ledgers
from verification.stage3 import bundle,C,MOD
from verification.stage2 import launch
from src.he import native
from src.hidden_cache import sources,load as load_hidden
from src.model import binding
from src.mpc import VERSION,ProtocolError,private_write


def share(values):
    first=[secrets.randbits(32) for _ in values]
    return first,[(v-a)%MOD for v,a in zip(values,first)]


def offline(directory,sid,plan):
    private_write(directory/'public-plan.json',dict(session=sid,bits=32,plan=plan))
    result=subprocess.run([sys.executable,'-m','src.offline',str(directory),str(directory/'public-plan.json')],
                          cwd=ISOLATED_ROOT,capture_output=True,text=True,check=True)
    return json.loads(result.stdout)


def run():
    n=7;width=C['model_reference']['hidden_width'];d,sid,public,_,p,t,_=bundle(n)
    public['data_moduli']=native(['metadata',d/'S0'])['data_moduli'];os.link(d/'S0/parameters.seal',d/'parameters.seal')
    model=binding(secrets.token_hex(16),public['node_order'],1,width,C['model_reference']['classes'],C['fraction_bits'])
    for role in (0,1):
        own=d/f'S{role}';layer=own/'he-layer0';layer.mkdir()
        for name in ('parameters.seal','eval.pk','eval.gk','peer.sk','rows','he.json'):(own/name).rename(layer/name)
        manifest=json.loads((layer/'he.json').read_text());manifest['public']=public
        (layer/'he.json').unlink();private_write(layer/'he.json',manifest)
        private_write(own/'input-shares.json',dict(fixture=role))
        private_write(own/('model-'+model['model_id']+'.json'),dict(fixture=role))
    binding_id=secrets.token_hex(32)
    op=dict(type='he_aggregate',conversion='private_decryption',count=n*width,fraction=C['fraction_bits'],
            k=C['mpc']['activation_range_bits'],activation='fss',he=public,he_slot='he-layer0',
            model=model,model_layer=0,cache_binding=binding_id,cache_capture=True,trace_ciphertexts=False)
    first_offline=offline(d,sid,[op]);values=[v for row in t for v in row];parts=share(values)
    for role in (0,1):
        job=copy.deepcopy(op);job['x']=parts[role]
        private_write(d/f'S{role}/input.json',dict(version=VERSION,session=sid,role=role,bits=32,operations=[job]))
    attempt,metrics=launch(d,sid,32,timeout=240)
    assert all(row['success'] for row in metrics),metrics
    captured=[json.loads((d/f'S{r}'/('first-layer-'+attempt+'.json')).read_text()) for r in (0,1)]
    assert all(row['asset_hashes']==sources(d/f'S{r}',model) for r,row in enumerate(captured))
    hidden=[(a+b)%MOD for a,b in zip(captured[0]['shares'],captured[1]['shares'])]
    expected=[max(0,sum((p[i][j] if p[i][j]<1<<31 else p[i][j]-MOD)*
                        (t[j][c] if t[j][c]<1<<31 else t[j][c]-MOD) for j in range(n))//(1<<C['fraction_bits']))%MOD
              for i in range(n) for c in range(width)]
    assert hidden==expected
    second=secrets.token_hex(16);other=ISOLATED_ROOT/'build/stage3'/second
    for role in (0,1):
        own=other/f'S{role}';own.mkdir(parents=True,mode=0o700)
        for name in ('input-shares.json','model-'+model['model_id']+'.json'):
            os.link(d/f'S{role}'/name,own/name)
        layer=own/'he-layer0';layer.mkdir()
        for file in (d/f'S{role}/he-layer0').rglob('*'):
            target=layer/file.relative_to(d/f'S{role}/he-layer0')
            if file.is_dir():target.mkdir(exist_ok=True)
            elif file.name not in ('features.bin','masks.bin') and not file.parent.name in ('send','trace','secure-products'):
                if file.relative_to(d/f'S{role}/he-layer0').parts[0] in ('rows','he.json','parameters.seal','eval.pk','eval.gk','peer.sk'):os.link(file,target)
        private_write(own/'hidden-state.json',captured[role])
    load=dict(type='load_hidden',count=n*width,cache_binding=binding_id,source_session=sid,model=model)
    plan=[load,dict(type='public_mul',count=n*width,scalar=1,use_previous=True)]
    second_offline=offline(other,second,plan)
    for role in (0,1):
        jobs=copy.deepcopy(plan);jobs[0]['x']=[];jobs[1]['x']=[]
        private_write(other/f'S{role}/input.json',dict(version=VERSION,session=second,role=role,bits=32,operations=jobs))
    fresh_attempt,fresh=launch(other,second,32,timeout=30)
    assert all(row['success'] for row in fresh),fresh
    outputs=[json.loads((other/f'S{r}'/('output-'+fresh_attempt+'.json')).read_text())['shares'][-1] for r in (0,1)]
    assert [(a+b)%MOD for a,b in zip(*outputs)]==expected
    assert all(row['preprocessing']['consumed']==second_offline['generated'] for row in fresh)
    tamper=ISOLATED_ROOT/'build/hidden-cache-tamper'/secrets.token_hex(16)
    shutil.copytree(other/'S0',tamper,copy_function=os.link)
    (tamper/'input-shares.json').unlink();private_write(tamper/'input-shares.json',dict(fixture='changed'))
    try:load_hidden(tamper,0,load,MOD)
    except ProtocolError as error:assert error.code=='HIDDEN_SOURCE_CHANGED',error.code
    else:raise AssertionError('changed input assets reused hidden state')
    return dict(status='PASS_FRESH_SESSION_HIDDEN_REUSE',source_session=sid,reuse_session=second,
                first_layer_online_bytes=sum(row['communication']['bytes_sent'] for row in metrics),
                reused_online_bytes=sum(row['communication']['bytes_sent'] for row in fresh),
                first_layer_rounds=metrics[0]['communication']['exchange_rounds'],
                reused_rounds=fresh[0]['communication']['exchange_rounds'],
                first_materials=first_offline['generated'],reused_materials=second_offline['generated'],
                exact_values=len(expected),changed_source_rejected=True,model_training_or_full_query=False)


if __name__=='__main__':
    result=run();out=Path(__file__).resolve().parents[1]/'results/final-experiments/hidden-cache-reuse.json'
    out.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
