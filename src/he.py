"""Real SEAL bridge and full-coefficient masked cross-key conversion.
No plaintext reconstruction or same-key secret access in server operations.
"""
import hashlib
import json
import os
import secrets
import struct
import subprocess
import time
from pathlib import Path
from .mpc import ROOT, ProtocolError, require

def file_hash(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def binary_write(path,data):
    with os.fdopen(os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600),'wb') as f:
        f.write(data);f.flush();os.fsync(f.fileno())
def native(args):
    env=os.environ.copy();env['LD_LIBRARY_PATH']=str(ROOT/'deps/toolchain/usr/lib/x86_64-linux-gnu')
    from .storage import check
    proc=subprocess.Popen([str(ROOT/'build/he_bridge')]+[str(a) for a in args],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,env=env)
    deadline=time.monotonic()+240
    try:
        while True:
            try:out,err=proc.communicate(timeout=.5);break
            except subprocess.TimeoutExpired:
                check(ROOT)
                if time.monotonic()>deadline:raise ProtocolError('HE_NATIVE_TIMEOUT')
    except BaseException:
        proc.terminate()
        try:proc.communicate(timeout=3)
        except subprocess.TimeoutExpired:proc.kill();proc.communicate()
        raise
    class Response:pass
    p=Response();p.returncode=proc.returncode;p.stdout=out
    if p.returncode: raise ProtocolError('HE_NATIVE_FAILURE')
    try:return json.loads(p.stdout)
    except ValueError: raise ProtocolError('HE_NATIVE_RESPONSE') from None

def aggregate(engine,own,op,x):
    """Returns raw S² shares. Truncation happens after both contributions combine."""
    started=time.perf_counter();own=Path(own);manifest=json.loads((own/'he.json').read_text());public=op['he'];n,c=public['shape'];degree=public['degree']
    if 'model' in op:
        model=op['model'];layer=op['model_layer'];features,hidden,classes=model['dimensions']
        require(layer in (0,1) and model['node_order']==public['node_order'] and model['fraction_bits']==op['fraction'] and c==(hidden if layer==0 else classes) and public['column_order']==([f'hidden-{j}' for j in range(hidden)] if layer==0 else model['class_order']),'HE_MODEL_BINDING')
    require(engine.bits==32 and len(x)==n*c and op['count']==n*c,'HE_INPUT_SHAPE')
    require(manifest['public']==public and manifest['role']==engine.role,'HE_INTERFACE_BINDING')
    require(len(public['node_order'])==n and len(set(public['node_order']))==n and len(public['column_order'])==c and len(set(public['column_order']))==c,'HE_ORDER_BINDING')
    if 'input_bound' in op:
        # Valid normalized nonnegative P has coefficients in [0,input_scale].
        # This input-preparation contract is not a proof about encrypted P.
        from .ranges import radius,bit_width
        require(1<=bit_width(op['input_bound'])<=engine.bits and n*public['input_scale']*radius(op['input_bound'])<1<<(engine.bits-1),'HE_PUBLIC_DOT_BOUND_UNSAFE')
    require(public['ring_bits']==engine.bits and public['input_scale']==1<<op['fraction'] and public['output_scale']==1<<(2*op['fraction']),'HE_SCALE_BINDING')
    require(not (own/'self.sk').exists(),'HE_FORBIDDEN_SAME_KEY_SECRET')
    # Local bundle integrity. Secret-key checksum stays private, never in messages/logs.
    for path,digest in manifest['local_integrity'].items():
        require((own/path).resolve().is_relative_to(own.resolve()),'HE_LOCAL_PATH_BINDING')
        require(file_hash(own/path)==digest,'HE_LOCAL_KEY_OR_PARAMETER_BINDING')
    ids,span=engine.materials.take('he_mask',c)  # durable consume before mask generation/open
    require(len(set(ids))==c,'HE_MASK_IDENTIFIER_REUSE')
    mask_started=time.perf_counter()
    mask=[secrets.randbits(32) for _ in range(c*degree)]
    binary_write(own/'features.bin',struct.pack('<'+'I'*len(x),*x))
    binary_write(own/'masks.bin',struct.pack('<'+'I'*len(mask),*mask))
    mask_generation_seconds=time.perf_counter()-mask_started
    profile=native(['eval',own,n,c]);profile['mask_generation_and_input_io_seconds']=mask_generation_seconds
    if op.get('conversion')=='private_decryption':
        from .he_secure import secure_convert
        result,converted=secure_convert(engine,own,op,mask,ids);profile.update(converted);profile.update(mask_coefficients=c*degree,mask_items_consumed=c,bridge_wall_seconds=time.perf_counter()-started)
        return result,profile
    require(op.get('conversion')=='legacy_ciphertext','HE_CONVERSION_TYPE')
    cts=[(own/'send'/f'{j}.ct').read_bytes() for j in range(c)]
    require(len(set(map(len,cts)))==1,'HE_PACKET_LENGTH')
    def header(role,nonce):return dict(version='privacy-gnn-he-convert-v1',session=engine.channel.session,operation=engine.op,role=role,key_id=public['key_ids'][role],package_id=public['package_id'],parameters_id=public['parameters_id'],shape=public['shape'],node_order=public['node_order'],column_order=public['column_order'],ciphertext_length=len(cts[0]),mask_ids=nonce)
    encoded=json.dumps(header(engine.role,ids),sort_keys=True,separators=(',',':')).encode();payload=struct.pack('!I',len(encoded))+encoded+b''.join(cts)
    # Key/mask ids have fixed length, so both parties' exact payload lengths agree.
    conversion_started=time.perf_counter();peer=bytes(engine.channel.exchange(engine.op,'he_masked_ciphertexts',[len(payload)],payload,'byte',span))
    require(len(peer)>4,'HE_PACKET_LENGTH');size=struct.unpack('!I',peer[:4])[0]
    require(size<=len(peer)-4,'HE_PACKET_HEADER');received=json.loads(peer[4:4+size]);nonces=received.get('mask_ids',[])
    require(len(nonces)==c and len(set(nonces))==c and all(isinstance(v,str) and len(v)==32 for v in nonces),'HE_PEER_MASK_IDENTIFIERS')
    require(received==header(1-engine.role,nonces),'HE_PEER_KEY_OR_ORDER_BINDING')
    require(len(peer)==4+size+c*len(cts[0]),'HE_PACKET_LENGTH')
    # Receiving material ids are bound to the session and already-reserved batch.
    # No resume: replay of any consumed batch is rejected before connection.
    engine.materials.claim_he_ids(nonces,'peer')
    (own/'receive').mkdir(mode=0o700)
    for j in range(c):binary_write(own/'receive'/f'{j}.ct',peer[4+size+j*len(cts[0]):4+size+(j+1)*len(cts[0])])
    decrypt=native(['decrypt',own,c]);raw=(own/'decrypted.bin').read_bytes();require(len(raw)==4*c*degree,'HE_DECRYPTED_SHAPE')
    decoded=struct.unpack('<'+'I'*(c*degree),raw)
    result=[(mask[col*degree+row]+decoded[col*degree+row])%engine.mod for row in range(n) for col in range(c)]
    profile.update(conversion_seconds=time.perf_counter()-conversion_started,decryption_seconds=decrypt['elapsed_seconds'],conversion_payload_bytes=len(payload),conversion_rounds=1,mask_coefficients=c*degree,mask_items_consumed=c,peak_rss_kib=max(profile['peak_rss_kib'],decrypt['peak_rss_kib']),bridge_wall_seconds=time.perf_counter()-started)
    return result,profile
