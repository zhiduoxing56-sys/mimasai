"""Read-only deployment evidence. Missing identities are blockers, never PASS.

No account/permission changes, no secret content reads, and no application
launch. The actual UID matrix remains NOT_RUN until privileged deployment.
"""
import collections,datetime,json,os,pwd,stat,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.mpc import ROOT
from src.storage import snapshot,committed

ROLES=('s0','s1','dealer','receiver','coordinator','page')
EXPERIMENT='a49152b33097752eaf81a7cba6d910a3'
RULES=[
    ('s0','S1 private material','DENY'),('s0','S1 consumption ledger','DENY'),
    ('s1','S0 private material','DENY'),('s1','S0 consumption ledger','DENY'),
    ('dealer','S0 input/model/messages','DENY'),('dealer','S1 input/model/messages','DENY'),
    ('dealer','receiver request directory','DENY'),('dealer','public plan','ALLOW'),
    ('receiver','this request authorized final exports','ALLOW'),('receiver','another request exports','DENY'),
    ('receiver','online inputs/models/ledgers','DENY'),
    ('coordinator','S0/S1 secrets/ledgers','DENY'),('coordinator','verification directory','DENY'),
    ('page','S0/S1 secrets/ledgers','DENY'),('page','verification directory','DENY'),
    ('page','filtered public status and authorized result interface','ALLOW')]

def main():
    identities={}
    for role in ROLES:
        try:
            entry=pwd.getpwnam('pgnn-'+role);identities[role]=dict(uid=entry.pw_uid,gid=entry.pw_gid)
        except KeyError:identities[role]=None
    missing=[role for role in ROLES if identities[role] is None]
    manifest=json.loads((ROOT/f'results/application/{EXPERIMENT}/manifest.json').read_text())
    root=ROOT/'build/application'/EXPERIMENT;checkpoint=Path(manifest['checkpoint']['directory'])
    inodes=collections.defaultdict(list);symlinks=[];ownership=collections.Counter()
    for base in (root,checkpoint):
        for directory,dirs,files in os.walk(base,followlinks=False):
            for name in dirs+files:
                path=Path(directory)/name
                if path.is_symlink():symlinks.append(str(path.relative_to(ROOT)))
            for name in files:
                path=Path(directory)/name
                if path.is_symlink():continue
                st=path.stat();ownership[(st.st_uid,stat.S_IMODE(st.st_mode))]+=1
                if st.st_nlink<=1:continue
                relative=path.relative_to(ROOT);domain=next((v for v in relative.parts if v in ('S0','S1','V')),'public')
                inodes[(st.st_dev,st.st_ino)].append(dict(path=str(relative),domain=domain,links=st.st_nlink))
    collisions=[aliases for aliases in inodes.values() if len({a['domain'] for a in aliases}&{'S0','S1','V'})>1]
    unresolved=[aliases for aliases in inodes.values() if aliases[0]['links']>len(aliases)]
    negative_control=[]
    model=manifest['publication']['models'][-1]['model_id']
    for path in (root/'S0'/f'model-{model}.json',root/'S1'/f'model-{model}.json',ROOT/'state/mpc/S0-ledger.sqlite',ROOT/'state/mpc/S1-ledger.sqlite',root/'V/data.json'):
        try:fd=os.open(path,os.O_RDONLY);os.close(fd);opened=True;reason=None
        except OSError as error:opened=False;reason=str(error)
        negative_control.append(dict(uid=os.geteuid(),path=str(path.relative_to(ROOT)),open_succeeded=opened,error=reason,secret_contents_read=False))
    result=dict(timestamp_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        status='BLOCKED_MISSING_OS_IDENTITIES' if missing else 'IDENTITIES_PRESENT_PERMISSION_MATRIX_STILL_REQUIRED',
        current_uid=os.getuid(),current_euid=os.geteuid(),identities=identities,missing=missing,
        matrix=[dict(role=role,uid=identities[role]['uid'] if identities[role] else None,resource=resource,expected=expected,actual='NOT_RUN_AS_ROLE') for role,resource,expected in RULES],
        common_uid_negative_control=negative_control,
        hardlink_metadata=dict(scope=[str(root.relative_to(ROOT)),str(checkpoint.relative_to(ROOT))],hardlinked_inodes=len(inodes),cross_secret_role_aliases=collisions,aliases_outside_scanned_roots=len(unresolved),outside_alias_examples=unresolved[:5],symlinks=symlinks,file_ownership=[dict(uid=uid,mode=oct(mode),files=count) for (uid,mode),count in ownership.items()],full_host_alias_audit=False),
        startup_fds=dict(source_inspection='runtime passes only each role socket; all launches close other descriptors and bind stdin to /dev/null',independent_same_uid_test='results/lifecycle/storage-checks.json',actual_role_uid_test='NOT_RUN'),
        existing_model=dict(experiment=EXPERIMENT,model_id=model,source_iteration=manifest['checkpoint']['iteration'],publication_committed=committed(manifest['publication']['session']),model_reconstructed=False,training_reexecuted=False),
        space=snapshot(ROOT),page=dict(status='NOT_CONNECTED_PERMISSION_GATE_UNMET',real_page_query='NOT_RUN'),
        boundary='Local deployment only; administrator retains access. Half-honest online parties and trusted offline generation boundary remain.')
    out=ROOT/'results/lifecycle';out.mkdir(parents=True,exist_ok=True)
    (out/'role-preflight.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(status=result['status'],current_uid=result['current_uid'],missing=missing,matrix='NOT_RUN_AS_ROLE',cross_secret_role_aliases=len(collisions),aliases_outside_scanned_roots=len(unresolved),page=result['page']),indent=2))
    return 2
if __name__=='__main__':raise SystemExit(main())
