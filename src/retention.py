"""Preview-first terminal-session cleanup. Preserve checkpoints and evidence."""
import argparse, hashlib, json, os
from pathlib import Path
from .mpc import ROOT,require
from .storage import lease,record,transition,TERMINAL

# Exact one-shot files, never model/key/config/output/checkpoint/ledger files.
def disposable(relative):
    parts=relative.parts
    if len(parts)<2 or parts[0] not in ('S0','S1'):return False
    if parts[1] in ('ring-preprocessing','secure-products','send','trace','receive'):return True
    if len(parts)==2:return parts[1] in ('preprocessing.json','input.json','features.bin','masks.bin','peer-key-coefficients.bin') or (parts[1].startswith('cipher-') and parts[1].endswith('.bin'))
    if parts[1] in ('he-layer0','he-layer1'):
        if parts[2] in ('secure-products','send','trace','receive'):return True
        if len(parts)==3:
            return parts[2] in ('features.bin','masks.bin','peer-key-coefficients.bin') or (parts[2].startswith('cipher-') and parts[2].endswith('.bin'))
    return False

def manifest(directory):
    directory=Path(directory)
    files=[]
    for path in sorted(directory.rglob('*')):
        relative=path.relative_to(directory)
        if not disposable(relative):continue
        require(not path.is_symlink(), 'CLEAN_SYMLINK_REJECTED')
        if path.is_file():
            st=path.stat();files.append(dict(path=str(relative),bytes=st.st_size,
                allocated_bytes=st.st_blocks*512,device=st.st_dev,inode=st.st_ino,mtime_ns=st.st_mtime_ns,links=st.st_nlink))
    # A hardlinked file is not counted as reclaimable unless all links are
    # removed; this intentionally underestimates savings.
    return dict(files=files,logical_bytes=sum(f['bytes'] for f in files),
                reclaimable_upper_bytes=sum(f['allocated_bytes'] for f in files if f['links']==1))

def preview(sid):
    with lease(sid):
        entry=record(sid);require(entry is not None,'SESSION_UNKNOWN')
        require(entry['state'] in TERMINAL,'SESSION_NOT_TERMINAL')
        directory=Path(entry['directory']);require(directory.is_relative_to(ROOT/'build'),'CLEAN_ROOT_REJECTED')
        result=dict(session=sid,batch=entry['batch'],state=entry['state'],directory=str(directory),**manifest(directory))
        result['digest']=hashlib.sha256(json.dumps(result,sort_keys=True).encode()).hexdigest()
        return result

def apply(preview_doc):
    sid=preview_doc['session']
    with lease(sid):
        entry=record(sid);require(entry and entry['state'] in TERMINAL,'SESSION_NOT_TERMINAL')
        directory=Path(entry['directory']);require(directory.is_relative_to(ROOT/'build'),'CLEAN_ROOT_REJECTED')
        current=dict(session=sid,batch=entry['batch'],state=entry['state'],directory=str(directory),**manifest(directory))
        require(hashlib.sha256(json.dumps(current,sort_keys=True).encode()).hexdigest()==preview_doc['digest'],'CLEAN_PREVIEW_CHANGED')
        # Persist terminal/cleaning intent BEFORE deleting a single byte. On
        # interruption retry produces a new preview of remaining files.
        termination=entry['state']
        if termination=='cleaned':
            prior=json.loads(entry['detail']);termination=prior.get('termination_state',prior.get('previous'))
        require(termination in ('completed','aborted'),'CLEAN_TERMINATION_UNKNOWN')
        transition(sid,TERMINAL,'cleaned',json.dumps(dict(termination_state=termination,manifest=preview_doc)))
        for row in current['files']:
            path=directory/row['path']
            require(path.resolve().is_relative_to(directory) and not path.is_symlink(),'CLEAN_PATH_REJECTED')
            path.unlink()
        fd=os.open(directory,os.O_RDONLY|os.O_DIRECTORY)
        try:os.fsync(fd)
        finally:os.close(fd)
        return dict(session=sid,state='cleaned',removed_files=len(current['files']),reclaimable_upper_bytes=current['reclaimable_upper_bytes'])

def auto(sid):
    # Uses the exact same preview/revalidation policy as the user-facing command.
    doc=preview(sid);return apply(doc)

def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    a=sub.add_parser('preview');a.add_argument('--session',required=True);a.add_argument('--output',required=True)
    a=sub.add_parser('apply');a.add_argument('--preview',required=True)
    args=p.parse_args()
    if args.command=='preview':
        result=preview(args.session);Path(args.output).write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps({k:v for k,v in result.items() if k!='files'},indent=2))
    else:print(json.dumps(apply(json.loads(Path(args.preview).read_text())),indent=2))
if __name__=='__main__':main()
