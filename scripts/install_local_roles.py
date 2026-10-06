"""Run interactively with sudo: checked, resumable local deployment, no training.

Never reads passwords. No sudoers rule, passwordless generic command, ledger
rebuild, database vacuum, history deletion, model reconstruction or VHD work.
"""
import argparse,datetime,grp,hashlib,json,os,pwd,secrets,shutil,stat,subprocess,sys
from pathlib import Path
sys.dont_write_bytecode=True
PROJECT=Path(__file__).resolve().parents[1];BASE=Path('/var/lib/privacy-gnn');OPT=Path('/opt/privacy-gnn');CODE=OPT/'code';ROLES=('s0','s1','dealer','receiver','coordinator','page');EID='a49152b33097752eaf81a7cba6d910a3'
sys.path.insert(0,str(PROJECT))
from src.public_projection import model
from src.storage import snapshot

def require(ok,message):
    if not ok:raise RuntimeError(message)
def sha(path):
    digest=hashlib.sha256()
    with path.open('rb') as stream:
        for data in iter(lambda:stream.read(1024*1024),b''):digest.update(data)
    return digest.hexdigest()
def run(args):return subprocess.run(args,check=True,text=True,capture_output=True).stdout
def git(*args):return run(['git','-c','safe.directory='+str(PROJECT),'-C',str(PROJECT),*args])
def actor_root(role):return BASE/'actors'/role
def secure_dir(path,uid=0,gid=0,mode=0o700):
    require(not path.is_symlink(),'Unexpected deployment directory symlink: '+str(path))
    path.mkdir(parents=True,exist_ok=True);os.chown(path,uid,gid);os.chmod(path,mode)
def atomic(path,doc):
    temp=path.with_name(path.name+'.pending');require(not temp.is_symlink(),'Unsafe pending path')
    with temp.open('w') as stream:json.dump(doc,stream,indent=2);stream.write('\n');stream.flush();os.fsync(stream.fileno())
    os.chmod(temp,0o600);os.replace(temp,path)
    fd=os.open(path.parent,os.O_DIRECTORY|os.O_RDONLY)
    try:os.fsync(fd)
    finally:os.close(fd)
def state_source(path):
    if path.exists():return path
    history=BASE/'admin/migration.json'
    if history.exists():
        for row in json.loads(history.read_text())['state_files']:
            if row['before']['path']==str(path):
                target=Path(row['after']['path'])
                require(target.is_file() and target.stat().st_ino==row['before']['inode'],'Interrupted migration inode mismatch')
                return target
    return path
def state_paths():
    paths=[state_source(PROJECT/f'state/mpc/S{n}-ledger.sqlite') for n in (0,1)]+[state_source(PROJECT/'state/storage/sessions.sqlite')]
    for directory in (PROJECT/'state/storage',PROJECT/'state/mpc'):
        paths.extend(p for p in directory.iterdir() if p.is_file())
    return paths
def assets(manifest):
    root=PROJECT/'build/application'/EID;binding=manifest['publication']['models'][-1]
    result={}
    for number in (0,1):
        source=root/f'S{number}';files=[source/'input-shares.json',source/'query-policy.json',source/f'model-{binding["model_id"]}.json']
        for layer in (0,1):
            base=source/f'he-layer{layer}'
            files+=[base/name for name in ('eval.pk','eval.gk','peer.sk','parameters.seal','he.json')]
            files+=[base/'rows'/f'{i}.ct' for i in range(64)]
        result['s'+str(number)]=files
    return result
def open_handles(paths):
    inodes={(p.stat().st_dev,p.stat().st_ino) for p in paths};found=[]
    for directory in Path('/proc').glob('[0-9]*/fd'):
        if directory.parent.name==str(os.getpid()):continue
        try:
            for fd in directory.iterdir():
                try:
                    st=fd.stat()
                    if (st.st_dev,st.st_ino) in inodes:found.append(dict(pid=int(directory.parent.name),fd=fd.name))
                except FileNotFoundError:pass
        except FileNotFoundError:pass
    require(not found,'State files are still open by processes: '+json.dumps(found))
def preflight():
    require(os.geteuid()==0,'Run this installer in your local terminal with sudo.')
    require(not git('status','--porcelain').strip(),'Commit/review the complete deployment code before installing.')
    manifest=json.loads((PROJECT/f'results/application/{EID}/manifest.json').read_text());public=model(manifest)
    require(public['model_id']=='829a29a6913d505e7167f418a94674ee','Unexpected published model')
    require(manifest['checkpoint']['iteration']==160,'Existing 160-step checkpoint required')
    checkpoint=Path(manifest['checkpoint']['directory']);require(checkpoint.is_relative_to(PROJECT/'build'),'Unexpected checkpoint root')
    for n in (0,1):require((checkpoint/f'S{n}'/('output-'+manifest['checkpoint']['attempt']+'.json')).is_file(),'Existing role checkpoint missing')
    files=assets(manifest);seen={}
    for role,paths in files.items():
        for path in paths:
            require(path.is_file() and not path.is_symlink(),'Missing/nonregular retained asset: '+str(path))
            key=(path.stat().st_dev,path.stat().st_ino);require(key not in seen or seen[key]==role,'Cross-role hardlinked secret asset');seen[key]=role
    ledgers=[state_source(PROJECT/f'state/mpc/S{n}-ledger.sqlite') for n in (0,1)];gate=state_source(PROJECT/'state/storage/sessions.sqlite')
    for path in ledgers+[gate]:require(path.is_file(),'Original durable state missing: '+str(path))
    open_handles(state_paths());require((PROJECT/'build/he_bridge').is_file(),'Retained native backend missing')
    require(Path('/run/systemd/system').is_dir(),'Systemd deployment is required; do not launch roles manually with inherited secret FDs.')
    run(['systemctl','show','--property=Version','--value'])
    target=BASE if BASE.exists() else Path('/var/lib');require(target.stat().st_dev==PROJECT.stat().st_dev,'State migration requires the same filesystem, no fallback ledger copy/reset.')
    space=snapshot(PROJECT);require(space['host_available_bytes'] is not None,'Host disk probe unreadable; refuse deployment admission.')
    require(space['internal_available_bytes']>2*1024**3 and space['host_available_bytes']>8*1024**3,'Deployment disk reserve unavailable')
    for role in ROLES:
        try:
            account=pwd.getpwnam('pgnn-'+role);require(account.pw_uid not in (0,PROJECT.stat().st_uid) and account.pw_shell=='/usr/sbin/nologin','Unsafe existing account: '+role)
        except KeyError:pass
    print(json.dumps(dict(preflight='PASS',model_id=public['model_id'],source_iteration=160,nodes=64,host_probe=space['host_status'],state_files_open=False),indent=2))
    return manifest,public,files
def account(role):
    try:return pwd.getpwnam('pgnn-'+role)
    except KeyError:
        run(['/usr/sbin/useradd','--system','--user-group','--no-create-home','--shell','/usr/sbin/nologin','pgnn-'+role]);return pwd.getpwnam('pgnn-'+role)
def symlink(target,path):
    if path.is_symlink():require(path.resolve()==target.resolve(),'Unexpected existing link: '+str(path));return
    require(not path.exists(),'Unexpected existing deployment path: '+str(path));path.symlink_to(target,target_is_directory=target.is_dir())
def migrate(source,target,role,records):
    uid=pwd.getpwnam('pgnn-'+role).pw_uid;gid=grp.getgrnam('pgnn-gate').gr_gid if role=='coordinator' else pwd.getpwnam('pgnn-'+role).pw_gid
    existing=next((row for row in records if row['before']['path']==str(source)),None)
    if source.is_symlink():
        require(source.resolve()==target and existing,'Unexpected migrated state link')
        if existing.get('content_preserved'):return
    if existing:
        before=existing['before']
        retained=source if source.exists() else target
        require(retained.is_file() and retained.stat().st_ino==before['inode'] and sha(retained)==before['sha256'],'Interrupted migration content mismatch')
    else:
        require(not target.exists(),'State destination already exists; do not overwrite a ledger.')
        before=dict(path=str(source),device=source.stat().st_dev,inode=source.stat().st_ino,bytes=source.stat().st_size,sha256=sha(source))
        existing=dict(before=before,after=dict(path=str(target)),phase='planned',content_preserved=False);records.append(existing)
        history=BASE/'admin/migration.json';doc=json.loads(history.read_text());doc['state_files']=records;atomic(history,doc)
    if source.exists() and not source.is_symlink():os.rename(source,target)
    for path in (target,source.parent,target.parent):
        fd=os.open(path,os.O_RDONLY|(os.O_DIRECTORY if path.is_dir() else 0))
        try:os.fsync(fd)
        finally:os.close(fd)
    os.chown(target,uid,gid);os.chmod(target,0o640 if role=='coordinator' else 0o600);symlink(target,source)
    after=dict(path=str(target),device=target.stat().st_dev,inode=target.stat().st_ino,bytes=target.stat().st_size,sha256=sha(target))
    require(before['sha256']==after['sha256'] and before['inode']==after['inode'],'Migration content/inode mismatch')
    existing.update(after=after,phase='complete',content_preserved=True)
    history=BASE/'admin/migration.json';doc=json.loads(history.read_text());doc['state_files']=records;atomic(history,doc)
def install(manifest,public,files):
    for unit in ('pgnn-page','pgnn-coordinator','pgnn-role-broker'):
        subprocess.run(['systemctl','stop',unit],capture_output=True)
    open_handles(state_paths())
    identities={role:account(role) for role in ROLES};require(len({p.pw_uid for p in identities.values()})==6,'Role UIDs must be distinct')
    for name,members in [('pgnn-gate','pgnn-s0,pgnn-s1,pgnn-dealer,pgnn-coordinator'),('pgnn-page-api','pgnn-coordinator,pgnn-page')]:
        try:grp.getgrnam(name)
        except KeyError:run(['/usr/sbin/groupadd','--system',name])
        run(['/usr/sbin/gpasswd','-M',members,name])
    secure_dir(BASE,mode=0o711);secure_dir(BASE/'actors',mode=0o711);secure_dir(BASE/'admin');secure_dir(OPT,mode=0o755)
    history=BASE/'admin/migration.json';migration=json.loads(history.read_text()) if history.exists() else dict(state_files=[],assets=[],hardlink_audit=dict(cross_secret_role_aliases=0,existing_aliases_preserved=True),passwords_saved=False)
    atomic(history,migration)
    revision=git('rev-parse','HEAD').strip();release=OPT/'releases'/revision
    if not release.exists():
        secure_dir(release,mode=0o755)
        names=git('ls-files','-z').split('\0');hashes=[]
        for name in names:
            if not name.startswith(('src/','config/','ui/')):continue
            source=PROJECT/name;require(source.is_file() and not source.is_symlink(),'Unsafe runtime source');target=release/name;target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(source,target);os.chmod(target,0o444);hashes.append(dict(path=name,sha256=sha(target)))
        token_path=PROJECT/'results/page/access-link.json';token_path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        os.chown(token_path.parent,PROJECT.stat().st_uid,PROJECT.stat().st_gid);os.chmod(token_path.parent,0o700)
        if token_path.exists():access=json.loads(token_path.read_text())['access']
        else:
            access=secrets.token_hex(32);atomic(token_path,dict(access=access,url='http://127.0.0.1:8765/#access='+access));os.chown(token_path,PROJECT.stat().st_uid,PROJECT.stat().st_gid)
        deployment=dict(public,operator_uid=PROJECT.stat().st_uid,original_workspace=str(PROJECT),code=str(CODE),access_sha256=hashlib.sha256(access.encode()).hexdigest())
        atomic(release/'config/deployment-public.json',deployment);atomic(release/'config/deployment-report.json',manifest)
        atomic(release/'config/source-manifest.json',dict(commit=revision,files=hashes,sha256=hashlib.sha256(json.dumps(hashes,sort_keys=True).encode()).hexdigest()))
        for directory,dirs,names in os.walk(release):
            os.chown(directory,0,0);os.chmod(directory,0o555)
            for name in names:os.chown(Path(directory)/name,0,0);os.chmod(Path(directory)/name,0o444)
    temp=OPT/'code.pending'
    if temp.exists() or temp.is_symlink():temp.unlink()
    temp.symlink_to(release,target_is_directory=True);os.replace(temp,CODE)
    secure_dir(OPT/'native/build',mode=0o755)
    if not (OPT/'native/build/he_bridge').exists():shutil.copyfile(PROJECT/'build/he_bridge',OPT/'native/build/he_bridge')
    os.chown(OPT/'native/build/he_bridge',0,0);os.chmod(OPT/'native/build/he_bridge',0o555)
    library=OPT/'native/deps/toolchain/usr/lib/x86_64-linux-gnu'
    if not library.exists():shutil.copytree(PROJECT/'deps/toolchain/usr/lib/x86_64-linux-gnu',library,symlinks=True)
    for directory,dirs,names in os.walk(OPT/'native'):
        os.chown(directory,0,0);os.chmod(directory,0o755)
        for name in names:
            path=Path(directory)/name
            if not path.is_symlink():os.chown(path,0,0);os.chmod(path,0o555 if name=='he_bridge' else 0o444)
    for role,p in identities.items():
        own=actor_root(role);secure_dir(own,gid=p.pw_gid,mode=0o750)
        for name in ('build','state','results'):secure_dir(own/name,p.pw_uid,p.pw_gid)
        for name in ('build/requests','state/mpc'):secure_dir(own/name,p.pw_uid,p.pw_gid)
        symlink(CODE/'config',own/'config');symlink(OPT/'native/deps',own/'deps');symlink(OPT/'native/build/he_bridge',own/'build/he_bridge')
        atomic(own/'permission-public-plan.json',dict(public=True,nodes=64));os.chmod(own/'permission-public-plan.json',0o444)
    symlink(CODE/'config',BASE/'admin/config');symlink(OPT/'native/deps',BASE/'admin/deps')
    secure_dir(BASE/'gate',identities['coordinator'].pw_uid,grp.getgrnam('pgnn-gate').gr_gid,0o2750)
    migrate(PROJECT/'state/storage/sessions.sqlite',BASE/'gate/sessions.sqlite','coordinator',migration['state_files']);atomic(history,migration)
    for path in (PROJECT/'state/storage').iterdir():
        if path.name=='sessions.sqlite' or path.is_symlink():continue
        require(path.is_file() and not path.is_symlink(),'Unexpected state side file')
        target=BASE/'gate'/path.name
        if not target.exists():os.rename(path,target);os.chown(target,identities['coordinator'].pw_uid,grp.getgrnam('pgnn-gate').gr_gid);symlink(target,path)
    for number,role in enumerate(('s0','s1')):
        p=identities[role];secure_dir(actor_root(role)/'build/assets',p.pw_uid,p.pw_gid);secure_dir(actor_root(role)/f'build/assets/S{number}',p.pw_uid,p.pw_gid)
        migrate(PROJECT/f'state/mpc/S{number}-ledger.sqlite',actor_root(role)/f'state/mpc/S{number}-ledger.sqlite',role,migration['state_files']);atomic(history,migration)
        for suffix in ('-wal','-shm','-journal'):
            side=PROJECT/f'state/mpc/S{number}-ledger.sqlite{suffix}'
            if side.exists() and not side.is_symlink():migrate(side,actor_root(role)/('state/mpc/'+side.name),role,migration['state_files'])
        source=PROJECT/f'build/application/{EID}/S{number}'
        for path in files[role]:
            target=actor_root(role)/f'build/assets/S{number}'/path.relative_to(source);target.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
            for ancestor in target.parents:
                if ancestor==actor_root(role)/'build/assets':break
                os.chown(ancestor,p.pw_uid,p.pw_gid);os.chmod(ancestor,0o700)
            before=sha(path)
            if not target.exists():os.link(path,target)
            require(target.stat().st_ino==path.stat().st_ino,'Retained asset inode mismatch');os.chown(target,p.pw_uid,p.pw_gid);os.chmod(target,0o600)
            require(before==sha(target),'Retained asset changed')
        messages=actor_root(role)/'build/permission-messages'
        if not messages.exists():messages.write_text('Permission fixture only; no protocol messages.\n');os.chown(messages,p.pw_uid,p.pw_gid);os.chmod(messages,0o600)
        migration['assets'].append(dict(role=role,files=len(files[role]),content_unchanged=True,reconstructed=False));atomic(history,migration)
    receiver=identities['receiver'];secure_dir(actor_root('receiver')/'results/application'/EID/'receiver',receiver.pw_uid,receiver.pw_gid)
    for name,current in [('permission-current',True),('permission-other',False)]:
        directory=actor_root('receiver')/name;secure_dir(directory,receiver.pw_uid if current else 0,receiver.pw_gid if current else 0)
        path=directory/'S0.json'
        if not path.exists():path.write_text('Permission fixture only; no probability shares.\n')
        os.chown(path,receiver.pw_uid if current else 0,receiver.pw_gid if current else 0);os.chmod(path,0o600)
    secure_dir(Path('/run/privacy-gnn'),mode=0o755);secure_dir(Path('/run/privacy-gnn/public'),identities['coordinator'].pw_uid,grp.getgrnam('pgnn-page-api').gr_gid,0o750)
    os.chmod(PROJECT,0o700) # All original verification/private aliases remain outside role access.
    migration.update(commit=revision,timestamp_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),identities={r:dict(uid=p.pw_uid,gid=p.pw_gid) for r,p in identities.items()},source_iteration=160,model_id=public['model_id'],original_project_mode='0700')
    atomic(history,migration)
    tmpfiles=Path('/etc/tmpfiles.d/privacy-gnn.conf')
    tmpfiles.write_text('d /run/privacy-gnn 0755 root root -\nd /run/privacy-gnn/public 0750 pgnn-coordinator pgnn-page-api -\n');os.chmod(tmpfiles,0o644)
    common='\n[Service]\nType=simple\nUMask=0077\nNoNewPrivileges=yes\nProtectSystem=strict\nProtectHome=read-only\nKillMode=control-group\nTimeoutStopSec=15\nRestart=on-failure\nEnvironment=PYTHONPATH=/opt/privacy-gnn/code PYTHONDONTWRITEBYTECODE=1 PGNN_GATE_DIR=/var/lib/privacy-gnn/gate WSL_DISTRO_NAME=GNN-Project\n'
    for name,module,role,writes in [('role-broker','role_broker',None,'/var/lib/privacy-gnn /run/privacy-gnn'),('coordinator','demo_coordinator','coordinator','/var/lib/privacy-gnn/actors/coordinator /var/lib/privacy-gnn/gate /run/privacy-gnn/public'),('page','demo_page','page','/var/lib/privacy-gnn/actors/page')]:
        dependency={'role-broker':'local-fs.target systemd-tmpfiles-setup.service','coordinator':'pgnn-role-broker.service','page':'pgnn-coordinator.service'}[name]
        text='[Unit]\nDescription=Privacy GNN '+name+'\nAfter='+dependency+'\n'+common
        if role:text+='User=pgnn-'+role+'\nGroup=pgnn-'+role+'\n'
        if role=='coordinator':text+='SupplementaryGroups=pgnn-gate pgnn-page-api\n'
        text+='Environment=PGNN_ROOT='+str(actor_root(role) if role else BASE/'admin')+'\nReadWritePaths='+writes+'\nWorkingDirectory='+str(actor_root(role) if role else BASE/'admin')+'\nExecStart=/usr/bin/python3 -m src.'+module+'\n\n[Install]\nWantedBy=multi-user.target\n'
        path=Path('/etc/systemd/system')/('pgnn-'+name+'.service');path.write_text(text);os.chown(path,0,0);os.chmod(path,0o644)
    run(['systemctl','daemon-reload']);run(['systemctl','enable','--now','pgnn-role-broker','pgnn-coordinator','pgnn-page'])
    print('Installed. Permissions NOT yet accepted; page stays disconnected. Access link is in results/page/access-link.json (operator-only, not a password).')
def verify():
    records=json.loads((BASE/'admin/migration.json').read_text());require(len({identity['uid'] for identity in records['identities'].values()})==6,'UID separation failed')
    for row in records['state_files']:
        require(row['content_preserved'] and row['before']['sha256']==row['after']['sha256'],'State migration proof failed');require(Path(row['after']['path']).stat().st_ino==row['after']['inode'],'Persistent inode changed')
    for unit in ('pgnn-role-broker','pgnn-coordinator','pgnn-page'):require(run(['systemctl','is-active',unit]).strip()=='active','Service is not active: '+unit)
    for unit,role in [('pgnn-role-broker',None),('pgnn-coordinator','coordinator'),('pgnn-page','page')]:
        pid=int(run(['systemctl','show',unit,'--property=MainPID','--value']).strip())
        fields={line.split(':',1)[0]:line.split(':',1)[1].strip() for line in Path(f'/proc/{pid}/status').read_text().splitlines() if ':' in line}
        require(int(fields['Uid'].split()[1])==(records['identities'][role]['uid'] if role else 0),'Service actual EUID mismatch: '+unit)
    for directory,dirs,files in os.walk(CODE):
        for name in files:
            st=(Path(directory)/name).stat();require(st.st_uid==0 and st.st_mode&0o222==0,'Runtime code/config is not root-owned read-only')
    print(json.dumps(dict(installation='VERIFIED',uid_roles=records['identities'],migration_preserved=True,permissions='PENDING_REAL_UID_AUDIT',page='DISCONNECTED_UNTIL_AUDIT'),indent=2))
def main():
    p=argparse.ArgumentParser(description=__doc__);group=p.add_mutually_exclusive_group(required=True)
    for name in ('check','install','verify'):group.add_argument('--'+name,action='store_true')
    a=p.parse_args();require(os.geteuid()==0,'Use sudo interactively in your local terminal; no password is accepted by this script.')
    if a.verify:verify()
    else:
        manifest,public,files=preflight()
        if a.install:install(manifest,public,files)
if __name__=='__main__':main()
