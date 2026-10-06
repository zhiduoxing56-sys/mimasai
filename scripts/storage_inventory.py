"""Read-only allocated-byte inventory; never reads shares or resets ledgers."""
import collections,hashlib,json,os,sqlite3,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.mpc import ROOT
from src.storage import snapshot,record
from src.retention import disposable

def category(path):
    parts=path.parts;name=path.name
    if 'state' in parts:return 'durable_ledgers_and_state'
    if name=='preprocessing.json' or 'ring-preprocessing' in parts:return 'one_shot_preprocessing'
    if name.startswith('output-') or name.startswith('model-') or 'representative' in parts and path.suffix=='.json' and 'build' in parts:return 'checkpoints_models_reference_traces'
    if 'build' in parts and ('seal' in parts or name in ('he_bridge','seal_probe') or path.suffix in ('.o','.a')):return 'compiled_builds'
    if 'build' in parts and (name in ('input.json','input-shares.json','job-template.json') or name.startswith('job-')):return 'one_shot_online_inputs'
    if 'build' in parts and ('secure-products' in parts or 'send' in parts or 'trace' in parts or 'receive' in parts or name in ('features.bin','masks.bin','peer-key-coefficients.bin') or name.startswith('cipher-')):return 'evaluation_work_files'
    if 'build' in parts and path.suffix in ('.seal','.sk','.pk','.gk','.ct'):return 'persistent_he_assets'
    if 'build' in parts and path.suffix=='.bin':return 'evaluation_or_validation_binary_files_preserved'
    if 'deps' in parts:return 'dependencies_and_archives'
    if 'results' in parts:return 'acceptance_evidence'
    return 'other_inputs_sources_configs'

def scan(root):
    totals=collections.defaultdict(lambda:dict(logical_bytes=0,allocated_bytes=0,files=0));seen=set();total=0
    for directory,dirs,files in os.walk(root,followlinks=False):
        dirs[:]=[d for d in dirs if d not in ('.agents','.codex','.aws')]
        for name in files:
            p=Path(directory)/name
            if p.is_symlink():continue
            st=p.stat();key=(st.st_dev,st.st_ino)
            if key in seen:continue
            seen.add(key);cat=category(p.relative_to(root));totals[cat]['logical_bytes']+=st.st_size;totals[cat]['allocated_bytes']+=st.st_blocks*512;totals[cat]['files']+=1;total+=st.st_blocks*512
    return dict(directory=str(root),allocated_bytes=total,categories=dict(totals),hardlinks_counted_once_within_tree=True)

def sessions(root):
    rows=[];ledgers=[]
    for role in (0,1):
        path=root/'state/mpc'/f'S{role}-ledger.sqlite'
        if path.exists():
            with sqlite3.connect(f'file:{path}?mode=ro',uri=True) as conn:
                ledgers.append({s:(b,state) for b,s,state in conn.execute('SELECT batch,session,state FROM batches')})
        else:ledgers.append({})
    discovered={}
    for name in ('public-plan.json','material-identifiers.json'):
        for meta in (root/'build').rglob(name):
            try:discovered[meta.parent]=json.loads(meta.read_text())['session']
            except (KeyError,ValueError):continue
    # Identify old one-shot bundles without reading their secret JSON payload.
    for material in (root/'build').rglob('preprocessing.json'):
        directory=material.parent.parent;sid=directory.name
        if material.parent.name in ('S0','S1') and len(sid)==32 and all(c in '0123456789abcdef' for c in sid):discovered.setdefault(directory,sid)
    for directory,sid in sorted(discovered.items()):
        states=[ledger.get(sid) for ledger in ledgers];terminal=all(s and s[1] in ('completed','aborted_burned') for s in states)
        known=record(sid) if root==ROOT else None
        files=[]
        for p in directory.rglob('*'):
            if p.is_file() and not p.is_symlink() and disposable(p.relative_to(directory)):
                st=p.stat();files.append(dict(path=str(p.relative_to(root)),bytes=st.st_size,allocated_bytes=st.st_blocks*512,links=st.st_nlink))
        rows.append(dict(session=sid,directory=str(directory),role_batch_states=states,lifecycle=known['state'] if known else 'UNKNOWN_LEGACY',
            status='KNOWN_TERMINAL_PREVIEW_ALLOWED' if known and known['state'] in ('completed','aborted','cleaned') else 'LEGACY_TERMINAL_EVIDENCE_REQUIRES_EXPLICIT_OFFLINE_RECONCILIATION' if terminal else 'REFUSE_UNKNOWN_OR_UNFINISHED',
            logical_bytes=sum(f['bytes'] for f in files),reclaimable_upper_bytes=sum(f['allocated_bytes'] for f in files if f['links']==1),files=files))
    return rows

def main():
    roots=[ROOT]+sorted(ROOT.parent.glob('privacy_gnn-replay-*'));out=ROOT/'results/storage';out.mkdir(parents=True,exist_ok=True)
    compiled=collections.defaultdict(list)
    for root in roots:
        for p in (root/'build').rglob('*'):
            if p.is_file() and not p.is_symlink() and category(p.relative_to(root))=='compiled_builds' and p.suffix not in ('.txt','.cmake'):
                st=p.stat();digest=hashlib.sha256(p.read_bytes()).hexdigest();compiled[(st.st_size,digest)].append(dict(path=str(p),allocated_bytes=st.st_blocks*512))
    duplicate_builds=[dict(bytes=key[0],sha256=key[1],copies=rows,redundant_allocated_bytes=sum(r['allocated_bytes'] for r in rows[1:])) for key,rows in compiled.items() if len(rows)>1]
    report=dict(timestamp=time.time(),capacity=snapshot(ROOT),trees=[scan(p) for p in roots],duplicate_compiled_files=duplicate_builds,duplicate_compiled_redundant_bytes=sum(r['redundant_allocated_bytes'] for r in duplicate_builds),historical_deletion_performed=False,
        scope='Allocated Linux blocks, unique inodes per tree; VHD logical file and host free measured separately; free Linux blocks do not imply host space reclaimed')
    (out/'inventory.json').write_text(json.dumps(report,indent=2)+'\n')
    history=[row for p in roots for row in sessions(p)]
    (out/'historical-preview.json').write_text(json.dumps(history,indent=2)+'\n')
    summary=dict(**report,historical_sessions=[{k:v for k,v in row.items() if k!='files'} for row in history])
    (ROOT/'docs/storage-inventory.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(dict(capacity=report['capacity'],trees=[(r['directory'],r['allocated_bytes']) for r in report['trees']],sessions=len(history),candidate_upper_bytes=sum(r['reclaimable_upper_bytes'] for r in history)),indent=2))
if __name__=='__main__':main()
