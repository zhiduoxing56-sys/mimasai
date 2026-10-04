from pathlib import Path
import hashlib,json,subprocess,sys
root=Path(__file__).resolve().parents[1];out=root/'results/stage3'
summary=json.loads((out/'summary.json').read_text());faults=json.loads((out/'faults-and-baseline.json').read_text())
def append(name,text):
 p=root/name;s=p.read_text();mark='## 阶段三第一轮'
 if mark in s:s=s[:s.index(mark)].rstrip()+'\n'
 p.write_text(s+'\n'+text.strip()+'\n')
materials=[]
for entry in json.loads((root/'results/material-manifest.json').read_text()):
 both=all(hashlib.sha256(p.read_bytes()).hexdigest()==entry['sha256'] for p in [root/'参考资料'/entry['file'],Path(entry['source'])]);assert both
 materials.append(dict(file=entry['file'],original_and_copy_unchanged=both))
(out/'material-integrity.json').write_text(json.dumps(materials,ensure_ascii=False,indent=2)+'\n')
sources=[]
for name,url,license in [('src/he_bridge.cpp','independent implementation; SEAL4.1.0 API and stage-zero trace derivation','project source'),('deps/SEAL-4.1.0/LICENSE','https://github.com/microsoft/SEAL/blob/v4.1.0/LICENSE','MIT'),('deps/downloads/arcedb-packlwes.cpp','https://github.com/zhouzhangwalker/ArcEDB/tree/e25a32dfb4a1585a95993f4b7ccd9c8f6afae4bc','MIT reference only, not linked'),('deps/downloads/BFV-ciphertext-simulatability-2025-203.pdf','https://eprint.iacr.org/2025/203','CC BY paper; no implementation copied')]:
 p=root/name;sources.append(dict(file=name,url=url,license=license,bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()))
(out/'sources.json').write_text(json.dumps(sources,ensure_ascii=False,indent=2)+'\n')
rows=[];overall=[]
for run in summary['runs']:
 a,b=run['servers'];ha=a['operations'][-1]['components'];hb=b['operations'][-1]['components'];pa=ha[0]['he_profile'];pb=hb[0]['he_profile']
 for key,label in [('multiply_seconds','HE ct×pt'),('extract_trace_seconds','ExtractConst+trace'),('pack_seconds','monomial packing'),('mask_generation_and_input_io_seconds','mask generation/input IO'),('full_mask_seconds','full coefficient subtraction')]:
  rows.append(dict(nodes=run['nodes'],activation=run['activation'],step=label,milliseconds=round(max(pa[key],pb[key])*1000,3),wire_bytes=0,rounds=0))
 rows.append(dict(nodes=run['nodes'],activation=run['activation'],step='cross-key conversion',milliseconds=round(max(pa['conversion_seconds'],pb['conversion_seconds'])*1000,3),wire_bytes=ha[0]['bytes_sent']+hb[0]['bytes_sent'],rounds=1))
 for xa,xb in zip(ha[1:],hb[1:]):
  rows.append(dict(nodes=run['nodes'],activation=run['activation'],step=xa['name'],milliseconds=round(max(xa['elapsed_seconds'],xb['elapsed_seconds'])*1000,3),wire_bytes=xa['bytes_sent']+xb['bytes_sent'],rounds=xa['rounds'],consumed=xa['consumed']))
 overall.append(dict(nodes=run['nodes'],activation=run['activation'],wire_bytes=run['wire_bytes'],rounds=run['rounds'],wall_seconds=run['wall_seconds'],peak_server_rss_kib=max(s['peak_rss_kib'] for s in run['servers']),peak_native_rss_kib=max(pa['peak_rss_kib'],pb['peak_rss_kib']),evaluation_key_bytes_per_group=run['setup']['evaluation_key_bytes']//2,consumed=a['preprocessing']['consumed'],min_noise_bits={s:v['min'] for s,v in run['he_oracle']['noise_bits'].items()}))
(out/'costs.json').write_text(json.dumps(dict(rows=rows,overall=overall),ensure_ascii=False,indent=2)+'\n')
report=dict(status='CORRECTNESS_AND_LOCAL_PROCESS_PASS_SECURITY_ACCEPTANCE_BLOCKED',homomorphic_hidden_runs=len(summary['runs']),recovered_test_values=sum(r['checks'] for r in summary['runs']),shared_baseline_runs=len(faults['shared_matrix_baseline']),negative_tests=len(faults['faults']),decoded_full_coefficients_masked=True,circuit_privacy=faults['circuit_privacy'],original_materials_unchanged=True,scope='No complete training, safe probability, secret indexing, hidden target query, or web')
(out/'acceptance.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
append('docs/interface.md','''## 阶段三第一轮：真实同态聚合与交叉转换（2026-10-04）

本轮接口保持阶段一节点顺序、公开零偏置和前置变换顺序。五节点先用原共享矩阵乘得到T0=floor(XW0/128)，直接把同一进程内T0份额送入同态聚合；不恢复或重新拆分T0。十六/三十二节点采用已处于尺度128的合成T夹具，验证聚合及后续算子，未宣称其完整模型线性层已运行。

唯一配置新增执行次数选择 he_execution_degree=8192（必须来自既有he_degrees）及测试规模[5,16,32]；ring32、fraction7、系数模数[55,55,54,54]、tc128不变。C++从可信参数文件创建SEALContext并再次执行tc128检查；不用BatchEncoder，明文模数2^32保持系数编码。

设归一化传播P已量化，邻域A_i=Σ_j P_ij x^(-j)，包含归一化对角权重。j>0的位置为8192−j且系数为−P_ij mod2^32，j=0直接编码。特征每列B_c=Σ_j T_jc x^j，可由整个32位环的任意份额构成。各服务器分别计算ct(A_i)×B_c自己的份额。ExtractConst取LWE常数样本；反向嵌入保留c1、仅保留c0[0]，各系数模数q下乘8192逆元，再按8193,4097,…,3进行13次Galois trace消去非目标项。每个标量同态乘x^i并相加，每列得到一个含N个节点结果的密文，剩余系数按正确性测试为0。纯求值进程不加载私钥，提取/打包不解密、不重加密。全零本地列以公钥生成新鲜零密文进入同样的提取打包路径；不关闭透明密文检查，也不通过解密产生零。

离线密钥设置端生成独立(pk0,sk0,gk0)、(pk1,sk1,gk1)。S0只加载pk0/gk0/邻域ct0与sk1；S1只加载pk1/gk1/邻域ct1与sk0。本轮不需要重线性化键，因为在线只有密文×明文。Galois键由对应私钥的KeyGenerator生成后分发。测试端V保留两私钥副本，仅为独立系数/噪声验证，不构成正式发布方。

每服务器每列生成8192个独立均匀r_i系数，覆盖整份可解密多项式；每批3列共24576系数。发送C_i=Enc_i(A_i贡献−r_i)。S0解密收到的C1得到v1=A1贡献−r1，输出s0=r0+v1；S1输出s1=r1+v0，故s0+s1=A0贡献+A1贡献=P(T0) mod2^32。有效位置按行主序恢复形状[N,3]；未使用位置也全部掩码，不能假设提取残留永远为零而省略保护。转换是一轮双向密文交换。

原始聚合结果尺度128²。两贡献转换成一个共享环值以后，调用原完整32位精确floor截断，随后批次范围检查及布尔或真实前缀DPF-FSS激活；禁止分别截断贡献。两次截断分别位于XW0和P(T0)之后，不能合并。HyGNN V-B Step1先同态线性/聚合、Step2转换（PDF第8页），本轮前置共享线性/截断并改用共享T本地明文乘法，工程编排不同；不宣称通信成本与论文一致。

消息沿用MPC版本、会话、操作序号、长度、形状、材料span；新增byte载荷，内层版本privacy-gnn-he-convert-v1绑定计算角色、随机package_id、公钥指纹key_id、参数文件摘要、节点/列顺序、[N,3]与固定密文长度。标识不依赖明文模型权重。本地私钥文件完整性摘要只留在私人包，不放消息或日志。检查可信包/消息绑定不构成恶意发送方密文属于该密钥的密码证明。

每列一枚随机he_mask标识，沿用整批离线保留账本；在线take先耐久消费，再用secrets生成完整系数掩码。local/peer标识另有跨批次唯一约束。失败后整批作废、重启拒绝；即使搬入新批次也拒绝旧标识。普通统计只含数量和公开元数据。state/mpc不得删除或回滚。

安全验收阻塞：以上代数保证和实测保证全部解码系数被掩码，但sub_plain不改变密文c1。持私钥接收方能查看密文及解密误差，普通BFV的IND-CPA不能证明其完整视图不泄露本地明文操作数。36项检查确认打包到掩码后c1保持不变（不是一个已证明的完整攻击）。未实现有安全参数和公开误差界的sanitization/噪声淹没或随机化求值，不能把该转换标为安全协议已验收。参考2025/203 §1.2（PDF第4–6页）的方案要求随机提升、平滑Gaussian及key switching随机化，不是普通Enc(0)或明文掩码就能替代。
''')
append('docs/trust.md','''## 阶段三第一轮持钥、数据与新增阻塞

两在线服务器继续半诚实、不串谋；可信离线三元组/daBit/FSS方只见公开计划并在在线输入存在前退出。独立离线密钥设置端在测试中加密已知图传播夹具并生成两组密钥；它不读取模型权重或在线T份额/转换消息。不自动将它与训练辅助方合并。验证端拥有合成图、参考数据和V测试私钥，只在独立测试中恢复和检查噪声；服务器没有恢复函数。

本轮实际持钥：S0持pk0/gk0与sk1，S1持pk1/gk1与sk0，不加载自身计算公钥对应私钥。Python读取审计拒绝另一角色和V目录，C++求值/解密分别按固定模式只打开自身计算材料或对方密钥；同Unix用户与应用审计仍不是OS隔离。在线服务器看到自己的份额/掩码、对方完整掩码密文及自己解密的完整掩码多项式、批次范围标志与公开尺寸/顺序/标识/计时。

全部明文系数均匀掩码保护已经验证；接收方持私钥时的密文与噪声视图隐私仍阻塞。128位SEAL参数检查保障的是参数层面的RLWE强度，不是电路隐私。没有悄悄增加“接收方只看解码明文”的信任假设来隐藏这一缺口。需在可信包、正确密钥设置、非串谋离线、不可回滚账本、无主动作弊的条件之外，解决该模拟/净化问题才能安全部署转换。
''')
append('docs/dependencies.md','''## 阶段三第一轮构建及协议来源

新增源码src/he_bridge.cpp，脚本sh scripts/build_stage3.sh复用项目内GCC13.3与静态SEAL4.1.0，不安装依赖、不调用挂载盘工具、不重建另一套SEAL参数。二进制build/he_bridge；Python桥src/he.py只用已有标准库。在线生成随机系数使用系统secrets，密钥及加密随机量使用SEAL默认密码随机工厂；未设置固定种子。所有新增源、下载论文及许可证摘要见results/stage3/sources.json。

提取/trace按阶段零已有独立实现及ArcEDB固定提交参考继续扩展，未链接ArcEDB代码。交叉持钥/转换依据HyGNN V-B Setup与Step2（PDF第7–8页），本轮扩充为完整多项式系数掩码。老师论文局部描述不提供普通SEAL求值密文的完整视图净化实现，记录为缺少协议细节。

补充原始来源：[Hwang、Min、Song，Ciphertext-Simulatable HE from BFV with Randomized Evaluation，2025/203](https://eprint.iacr.org/2025/203)，原文§1.1/§1.2说明HE的IND-CPA不足以推出2PC中求值方输入隐私；给出需要逐步随机化的构造。论文CC BY，仅下载和分析，未复制实现或宣称已完成适配。PDF与提取文本已保存。不能依据本次噪声余量选择“安全”噪声淹没幅度：还需公开最坏误差界、统计安全参数、余量及SEAL模链适配。

GitHub网页工具首次获取SEAL/ArcEDB指定页面返回cache miss，采用已有固定版本本地源码依据；ePrint主页面查询与原PDF下载成功。下载曾被沙箱代理拒绝，经批准联网后成功，未把失败获取计为成功。
''')
table='| 节点 | 激活 | 总字节 | 轮数 | 在线墙钟秒 | Python峰值KiB | Native峰值KiB |\n|---:|---|---:|---:|---:|---:|---:|\n'
for r in overall:table+=f"| {r['nodes']} | {r['activation']} | {r['wire_bytes']} | {r['rounds']} | {r['wall_seconds']:.3f} | {r['peak_server_rss_kib']} | {r['peak_native_rss_kib']} |\n"
step_table='| 节点/激活 | 操作 | ms | 双向字节 | 轮数 |\n|---|---|---:|---:|---:|\n'
for r in rows:step_table+=f"| {r['nodes']}/{r['activation']} | {r['step']} | {r['milliseconds']} | {r['wire_bytes']} | {r['rounds']} |\n"
append('docs/verification.md','''## 阶段三第一轮实际正确性与成本

入口sh scripts/run_stage3.sh（构建、六个闭环、故障与共享矩阵对照）；--smoke只跑五节点两条路径。结果results/stage3/summary.json、faults-and-baseline.json、costs.json及acceptance.json。汇总安全状态为阻塞，不以正确性PASS代替安全验收。

全部运行是本机独立进程。五节点包含XW0共享乘法和第一次精确截断；十六/三十二节点从预先处于尺度128的共享T夹具开始。三列分别打包，每列一次密文，两个方向共6份密文。每个规模有效系数、非目标零系数以及掩码后的全部49152系数均由V验证；归一化对角权重、孤立节点、零权重填充和负数T正确。全环均匀随机份额、四类环边界本地份额与全零本地份额另通过。先转换合并两贡献再一次floor截断，原共享矩阵对照在三规模通过。

总成本包含一次握手与五节点的前置线性；每列密文393329字节，13个Galois元素。每组评估键20517231字节、两组41034462字节；离线公钥/私钥/邻域密文分发不计入在线字节，其大小、生成时间和RSS已在setup字段记录。在线墙钟包括启动、文件读取、耐久账本与等待，分项ms取两方较大值，部分计时嵌套且不应盲目相加。峰值是各类进程RSS的较大值，不是全机同时总内存。Native求值使用逐步trace测试输出文件，性能含测试IO，不声称生产成本。

'''+table+'\n'+step_table+'''
逐步噪声由独立V持测试私钥检查，服务器普通日志不调用噪声接口。每次邻域密文、所有乘明文/提取结果和最终打包/掩码结果均检查；最小值及样本数见summary.json。结果仅证明夹具实际解密正确和余量为正，不是全输入最坏噪声界或电路隐私证明。

故障：节点/列顺序绑定、密钥/参数不匹配、同批重复掩码编号、完整转换交换后断连、新批次掩码编号重用共7项明确失败；前六项重启拒绝且无输出。旧阶段二乘法/精确截断215+5440输出与13类故障回归通过；激活真实密钥1524、小环5440、20越界批次及原故障继续通过，日志分别stage3-stage2-regression.log和stage3-stage2-round2-regression.log。

36次完整掩码前后c1比较保持相同，证据在faults-and-baseline.json。这证明明文掩码没有净化整个密文，不单独证明可恢复秘密，但足以拒绝将“所有系数已掩码”当成持私钥接收者完整视图安全证明。真实同态和数值闭环通过；安全转换验收仍阻塞。
''')
append('docs/acceptance.md',f'''## 阶段三第一轮验收（2026-10-04）

结论：真实同态算术、独立进程交叉转换的数值闭环通过；完整安全转换验收阻塞于密文视图隐私。具体状态CORRECTNESS_AND_LOCAL_PROCESS_PASS_SECURITY_ACCEPTANCE_BLOCKED，不能简写为安全协议全部通过。

已实际完成六个隐藏层闭环（5/16/32节点×布尔/FSS），独立验证端共核对{report['recovered_test_values']}项共享测试恢复值；五节点共享X/W0直连T0和两次精确截断，其他规模从尺度128共享T输入开始。三个共享矩阵独立对照通过。各服务器只加载自己的份额、计算公钥/评估键和交叉私钥，模型没有恢复给服务器或模型拥有者。

全部多项式可解密系数均独立掩码，包含非目标位置；全环随机、边界及全零本地份额通过，透明密文检查和tc128保持开启。7项新故障及旧共享/激活/截断回归通过。密钥大小、阶段计时、字节、轮数、内存、材料消耗和逐步骤噪声保存在results/stage3。原文件与项目参考资料3/3哈希不变。

仅为测试夹具的信息：完整合成图、归一化P、阶段一明文数值模型和宽整数范围oracle、测试端两私钥。密态服务器实际完成共享XW0、同态ct×pt、ExtractConst/trace/打包、全系数掩码、交叉解密到共享、精确截断、共享范围检查与两条激活。测试恢复和噪声检查不是服务器功能，也不是密态训练或发布成果。

必须先解决：普通BFV求值的持私钥接收者密文/噪声视图净化与安全依据；真实乘积/累加的共享溢出保障；训练数值与保持共享发布/跨环转换；身份认证、主动安全、OS隔离及账本回滚防护；预处理角色组合。现有缩位检查只能检查当前环值，不能追溯溢出。

建议下一轮优先核实能覆盖明文乘法和Galois trace的净化/随机化求值协议及参数，完成独立密文视图实验和安全分析后再决定实现路径；不直接接完整模型推理或训练。本轮停止，不实现安全概率、秘密索引、隐藏查询或网页。
''')
append('docs/issues.md','''## 阶段三第一轮问题更新

影响安全或正确性（新增硬阻塞）：全系数明文掩码不是密文视图净化；普通SEAL BFV的IND-CPA不保证持私钥接收者看不出本地操作数信息。36次检查显示c1未改变；完整simulatability/sanitization路径、误差界和参数未落实。不能临时增加“只看解码明文”的假设，不能用普通Enc(0)或实测噪声余量冒充证明。对应模块安全部署前必须解决。

已解决正确性与工程接口：真实同态多节点多列提取打包、交叉密钥分发、全部多项式系数掩码转换、合并两贡献后精确截断、两条激活及共享矩阵对照；随机标识和消费状态跨批次重用拒绝。参数/公钥摘要只绑定公开材料，未引入明文模型参数摘要。

继续阻塞：此前整数溢出保障、训练精度/算子、跨环保持共享发布、秘密索引、安全概率、隐藏查询、角色合并与部署认证/主动防护。接口完整性检查不等于恶意方密钥正确性证明。

后续优化：trace每节点13次Galois求值，评估键每组约20.5MB；三列每方约1.18MB转换载荷，测试trace文件IO影响耗时。可研究批量提取打包、列融合和净化路径，但不得改变两次截断位置、环尺度或完整系数掩码要求，不声称论文通信成本已经复现。
''')
append('docs/specification.md','''## 阶段三第一轮实现状态与材料对应

比赛3.3与HyGNN III-C/IV-B提供邻域多项式和提取打包依据；已真实实现多节点、三列BFV ct×pt、提取/trace与打包。HyGNN V-B Setup/Step2提供交叉私钥及转换代数依据；已落实正确性与全系数掩码，但密文视图安全依据仍缺失。提取trace、包/顺序绑定、完整系数随机掩码与前置共享线性后分别截断属于本轮明确实现选择。两条激活仍保持阶段二定义，图/model语义不变。

独立进程算子闭环已运行，验收报告区分正确性通过与安全阻塞。没有将此阶段写为完整低交互推理、密态训练或安全发布完成。原材料、旧共享矩阵聚合及旧验证入口保留。
''')
p=root/'README.md';s=p.read_text().replace('阶段零至阶段二第二轮','阶段零至阶段三第一轮');mark='阶段三第一轮入口：'
if mark in s:s=s[:s.index(mark)].rstrip()+'\n'
p.write_text(s+'\n阶段三第一轮入口：`sh scripts/run_stage3.sh`（`--smoke`只跑五节点）。真实SEAL聚合、交叉转换、精确截断和两条激活在5/16/32节点通过数值闭环；详见 [验收报告](docs/acceptance.md) 与 `results/stage3/acceptance.json`。全部解码系数已掩码，但持私钥接收者的密文视图隐私仍是安全验收阻塞。未改变模型语义或进入完整训练。\n')
print(json.dumps(report,ensure_ascii=False,indent=2))
