"""Summarize existing real test results; never generates protocol success data."""
from pathlib import Path
import datetime,hashlib,json,sys
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'results/continuation'
def read(name):return json.loads((ROOT/name).read_text())
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def compact(d):
 servers=d['servers'];dealer=d.get('dealer',d.get('offline'))
 return dict(status=d['status'],session=d['session'],wire_bytes=d['wire_bytes'],rounds=d['rounds'],offline=dealer['generated'],peak_server_rss_kib=max(s['peak_rss_kib'] for s in servers),operations=[dict(type=a['type'],wire_bytes=a['bytes_sent']+b['bytes_sent'],rounds=a['rounds'],seconds=max(a['elapsed_seconds'],b['elapsed_seconds']),consumed=a['consumed'],components=a['components']) for a,b in zip(servers[0]['operations'],servers[1]['operations'])])
names=['operators','training','training-indexed','publication','publication-indexed','targeted-checks','two-layer-he']
data={n:read('results/continuation/'+n+'.json') for n in names}
assert all(d['status'].startswith('PASS') for d in data.values())
old={n:read('results/'+n+'/summary.json') for n in ['stage2','stage2-round2']};assert all(d['status'].startswith('PASS') for d in old.values())
materials=[]
for item in read('results/material-manifest.json'):
 assert all(digest(path)==item['sha256'] for path in [ROOT/'参考资料'/item['file'],Path(item['source'])])
 materials.append(dict(file=item['file'],original_and_copy_unchanged=True))
sources=[]
for path,url,license in [('deps/downloads/seaf-fp-math.cpp','https://github.com/geralt-tian/SEAF/blob/dc264a421ea094984d2f4ad1b344f3a00062dfbe/SCI/src/Math/fp-math.cpp','MIT; reference only, not linked'),('deps/downloads/seaf-fixed-point.cpp','https://github.com/geralt-tian/SEAF/blob/dc264a421ea094984d2f4ad1b344f3a00062dfbe/SCI/src/FixedPoint/fixed-point.cpp','MIT; reference only, not linked'),('deps/downloads/seaf-LICENSE','https://github.com/geralt-tian/SEAF/blob/dc264a421ea094984d2f4ad1b344f3a00062dfbe/LICENSE','MIT'),('deps/downloads/oblivious-data-author-ch5.pdf','https://securecomputation.org/docs/ch5-obliviousdata.pdf','Author-distributed text; read only; no implementation copied'),('deps/downloads/BFV-ciphertext-simulatability-2025-203.pdf','https://eprint.iacr.org/2025/203','CC BY paper; no implementation copied')]:
 p=ROOT/path;sources.append(dict(file=path,url=url,license=license,sha256=digest(p),bytes=p.stat().st_size))
baseline=read('results/continuation/baseline-files.json');changed=[]
for folder in ['src','verification','scripts','docs','config']:
 for p in sorted((ROOT/folder).rglob('*')):
  if p.is_file() and '__pycache__' not in p.parts:
   name=str(p.relative_to(ROOT));h=digest(p)
   if baseline.get(name)!=h:changed.append(dict(file=name,baseline_sha256=baseline.get(name),sha256=h))
checks=data['targeted-checks'];pub=data['publication-indexed'];train=data['training-indexed']
report=dict(status='PASS_CONSTRAINED_MPC_TRAIN_PUBLISH_INFER_HE_SECURITY_BLOCKED',generated_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),material_integrity=materials,changed_files=changed,sources=sources,fetch_failures=[dict(url='https://eprint.iacr.org/2014/137.pdf',result='HTTP 403; used author Chapter 5 full-scan source; did not claim original ORAM reproduction')],training={n:dict(**compact(data[n]),losses=data[n]['losses'],gradient_float_max_error=data[n]['first_gradient_float_max_error'],precision_study=data[n]['precision_study']) for n in ['training','training-indexed']},publication={n:dict(**compact(data[n]),source_training_session=data[n]['source_training_session'],probability_error=data[n]['probability_error'],probability_sums=data[n]['probability_sums'],classification_equal=data[n]['classification_equal']) for n in ['publication','publication-indexed']},two_layer_he=[dict(**compact(r),he_oracle=r['he_oracle'],privacy=r['privacy'],wall_seconds=r['wall_seconds']) for r in data['two-layer-he']['runs']],stage3_hidden_costs=read('results/stage3/costs.json'),operator_tests=dict(status=data['operators']['status'],checks=sum(r['checks'] for r in data['operators']['runs']),probability=data['operators']['probability'],failed_domain_batches=len(data['operators']['failures'])),numeric_checks=dict(status=checks['status'],approximation_grid=checks['approximation_grid'],gradient_choice=checks['gradient_choice'],reference_view=checks['reference_view'],model_faults=checks['model_faults'],domain_failures=checks['failures'],public_unsafe_bounds=checks['public_unsafe_bounds']),old_regressions={n:d['status'] for n,d in old.items()},scope='Local independent processes, passive noncolluding servers, trusted noncolluding offline; pre-normalized input graph, public shape/order/mask; no active authentication',blockers=['BFV converter recipient ciphertext/noise-view privacy and justified randomization parameters','Private graph normalization incl inverse sqrt and secret-share to HE neighborhood publication','Cross-ring protected conversion beyond same-ring floor/scale multiplication','Broad-dimension training precision/range beyond conservative current 32/12 envelope','Optimized SecGNN auxiliary access and DCF kernels not reproduced; independent fullscan/prefix-DPF alternatives explicitly recorded','Hidden target query, active authentication, OS role isolation, and host ledger rollback resistance'],cost_convention='Bidirectional bytes including frames/hello; one synchronous exchange one round; op wall=max(server), includes persistent ledger IO; tests may overlap and are not isolated benchmarks; offline material/key bytes separate; RSS per process, not sum of machine memory')
(OUT/'acceptance.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
rows=[]
for label,d in [('密集共享训练3轮',data['training']),('秘密索引训练3轮',train),('训练份额发布→推理→概率',pub)]:
 c=compact(d);seconds=sum(op['seconds'] for op in c['operations']);rows.append(f"| {label} | {c['wire_bytes']:,} | {c['rounds']} | {seconds:.3f} | {c['peak_server_rss_kib']} |")
text='''# 持续推进实际验收（2026-10-04）

状态：受范围约束的小图MPC训练—持续共享发布—两层MPC推理—秘密概率闭环通过；真实同态两层算术通过，转换安全验收仍阻塞。协议/范围推导及未完成部分见 [continuation.md](continuation.md)。

本报告由 scripts/report_continuation.py 读取真实结果生成，不产生测试成功数据。完整机器可读成本、来源哈希、实际会话、材料消费与阻塞见 results/continuation/acceptance.json。复跑入口 sh scripts/run_continuation.sh，单独入口见实现说明；私有会话与账本不得纳入提交。

| 单元 | 双向字节 | 交互轮 | 操作时间秒 | 单服务器峰值KiB |
| --- | ---: | ---: | ---: | ---: |
'''+ '\n'.join(rows)+f'''

秘密索引路径三轮损失 {train['losses']}；梯度相对浮点初始参考最大差 {train['first_gradient_float_max_error']:.9g}，不是近似损失精确导数。发布后概率最大误差 {pub['probability_error']:.9g}；概率和 {pub['probability_sums']}；分类一致 {pub['classification_equal']}。所有前向状态、定点梯度、更新权重与独立定点参考逐项相同。

真实HE隐藏层沿用5/16/32节点六组结果，最低噪声余量91位；新五节点两层布尔/FSS路径均检查所有可解密系数及各阶段噪声。完整系数掩码不构成持私钥密文视图净化。该安全阻塞未被共享矩阵对照覆盖。

新增 {report['operator_tests']['checks']} 项原语输出检查；模型接口故障 {len(checks['model_faults'])} 项、概率/标签/范围故障 {len(checks['failures'])} 项、公开不安全累加界拒绝 {len(checks['public_unsafe_bounds'])} 项。旧精确截断/共享乘法及FSS/范围/故障检查全部再次通过。消费账本保留；恢复仅由验证端执行；原材料及副本 {len(materials)}/{len(materials)} 哈希一致。

性能口径：双向帧总字节含hello和头，交换算一轮；时间取双方较大值，含耐久账本I/O，测试可能并行，非隔离基准。离线材料与评估键另列，RSS是单进程峰值，不是整机总峰值。正确性测试不能替代安全证明。HE安全阻塞、私人图归一化和部署认证尚未完成，不称完整比赛系统完成。
'''
(ROOT/'docs/continuation-acceptance.md').write_text(text)
print(json.dumps(dict(status=report['status'],losses=train['losses'],probability_error=pub['probability_error'],materials=len(materials),changed_files=len(changed)),ensure_ascii=False,indent=2))
