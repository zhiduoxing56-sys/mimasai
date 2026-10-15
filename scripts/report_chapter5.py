"""Render Chapter 5 aggregate tables and SVGs from retained measured records."""
import csv
import html
import json
import shutil
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.data import cora
from src.metrics import evaluate
from src.sparse_reference import sparse,step

EXPERIMENT='a49152b33097752eaf81a7cba6d910a3'
RAW=ROOT/'results/final-experiments'
OUT=ROOT/'results/chapter5'

def read(path):return json.loads(Path(path).read_text())
def latest(pattern):
    candidates=[p for p in RAW.glob(pattern) if p.is_file() and '.failed.' not in p.name]
    if '-*.json' in pattern:
        older=RAW/pattern.replace('-*.json','.json')
        if older.is_file():candidates.append(older)
    return read(max(candidates,key=lambda p:p.stat().st_mtime)) if candidates else None
def write_csv(name,rows):
    if not rows:return
    with (OUT/name).open('w',newline='',encoding='utf-8-sig') as file:
        w=csv.DictWriter(file,fieldnames=list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)
def fmt(value,digits=3):return '—' if value is None else f'{value:.{digits}f}'
def clean(value):return html.escape(str(value))

def plot(name,title,subtitle,series,xlabel,ylabel):
    """Dependency-free publication-size vector chart; source is saved JSON only."""
    width,height=1500,800;left,right,top,bottom=125,50,145,115
    items=[(label,color,points) for label,color,points in series if points]
    if not items:return
    allpoints=[p for _,_,points in items for p in points]
    lo=min(x for x,y in allpoints);hi=max(x for x,y in allpoints)
    ymin=min(0,min(y for x,y in allpoints));ymax=max(y for x,y in allpoints)
    if hi==lo:hi=lo+1
    if ymax==ymin:ymax=ymin+1
    chartw=width-left-right;charth=height-top-bottom
    sx=lambda x:left+(x-lo)/(hi-lo)*chartw
    sy=lambda y:height-bottom-(y-ymin)/(ymax-ymin)*charth
    out=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img">',
         f'<title>{clean(title)}</title>',
         '<style>text{font-family:"Microsoft YaHei","Noto Sans CJK SC",sans-serif;fill:#17324d}.title{font-size:38px;font-weight:700}.sub{font-size:20px;fill:#52677a}.axis{font-size:20px}.legend{font-size:21px}.tick{font-size:17px}</style>',
         '<rect width="100%" height="100%" fill="#fff"/>',
         f'<text x="{left}" y="62" class="title">{clean(title)}</text>',
         f'<text x="{left}" y="104" class="sub">{clean(subtitle)}</text>']
    for i in range(6):
        value=ymin+(ymax-ymin)*i/5;y=sy(value)
        out.extend([f'<line x1="{left}" x2="{width-right}" y1="{y:.1f}" y2="{y:.1f}" stroke="#dbe5ec"/>',
                    f'<text x="{left-16}" y="{y+6:.1f}" class="tick" text-anchor="end">{value:.2f}</text>'])
    for i in range(5):
        value=lo+(hi-lo)*i/4;x=sx(value)
        out.append(f'<text x="{x:.1f}" y="{height-bottom+32}" class="tick" text-anchor="middle">{value:g}</text>')
    out.extend([f'<line x1="{left}" y1="{top}" x2="{left}" y2="{height-bottom}" stroke="#17324d" stroke-width="2"/>',
                f'<line x1="{left}" y1="{height-bottom}" x2="{width-right}" y2="{height-bottom}" stroke="#17324d" stroke-width="2"/>',
                f'<text x="{width/2}" y="{height-30}" class="axis" text-anchor="middle">{clean(xlabel)}</text>',
                f'<text x="{left}" y="{top-12}" class="axis">{clean(ylabel)}</text>'])
    for index,(label,color,points) in enumerate(items):
        poly=' '.join(f'{sx(x):.1f},{sy(y):.1f}' for x,y in points)
        out.append(f'<polyline points="{poly}" fill="none" stroke="{color}" stroke-width="4"/>')
        for x,y in points:out.append(f'<circle cx="{sx(x):.1f}" cy="{sy(y):.1f}" r="6" fill="{color}"/>')
        lx=left+index*400
        out.extend([f'<line x1="{lx}" x2="{lx+35}" y1="{height-78}" y2="{height-78}" stroke="{color}" stroke-width="5"/>',
                    f'<text x="{lx+48}" y="{height-71}" class="legend">{clean(label)}</text>'])
    out.append('</svg>')
    (OUT/name).write_text('\n'.join(out)+'\n')

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    source=ROOT/'results/application'/EXPERIMENT
    summary=read(source/'summary.json');train=read(source/'training/reference.json')
    if summary['training_steps']!=train['secure_steps'] or summary['model_id']!='829a29a6913d505e7167f418a94674ee':
        raise RuntimeError('retained chain binding changed')
    actual=read(ROOT/'results/representative/actual-checkpoints.json')['records'][-1]['metrics']
    published=summary['effects']['published_model_metrics']
    if any(actual[name]['accuracy']!=published[name]['accuracy'] for name in ('train','validation','test')):
        raise RuntimeError('published checkpoint metrics mismatch')
    float160=None
    checkpoint=ROOT/'build/representative/h6-lr0.5-seed20261005.json'
    if checkpoint.is_file():
        data=cora(node_count=64,sampling='stratified_frontier',seed=20261005)
        weights=read(checkpoint)['160']
        trace,_,_=step(sparse(data['propagation']),sparse(data['features']),weights,
                       data['labels'],[i in data['splits']['train'] for i in range(64)])
        measurements=evaluate(data,trace['probabilities'])
        float160={name:{key:measurements[name][key] for key in ('count','accuracy','macro_f1')}
                  for name in ('train','validation','test')}
    costs=summary['costs'];steps=train['secure_training']
    training=dict(status='REUSED_160_REAL_UPDATES',nodes=64,dimensions=summary['dimensions'],
                  train_count=actual['train']['count'],validation_count=actual['validation']['count'],
                  test_count=actual['test']['count'],
                  secure_model={name:{key:actual[name][key] for key in ('count','accuracy','macro_f1')}
                                for name in ('train','validation','test')},
                  float_checkpoint160_posthoc=float160,
                  float_selected320_test_accuracy=train['float_test_accuracy'],
                  training_online_seconds=costs['training_launch_seconds'],
                  training_online_wire_bytes=costs['training_online_bytes'],
                  training_offline_seconds=costs['training_offline_seconds'],
                  initial_secure_loss=steps[0]['loss'],final_secure_loss=steps[-1]['loss'],
                  condition='64-node label-stratified induced Cora; 551-6-7; 28/14/22 split; same seed and fixed nodes for checkpoint160 diagnostic')
    write_csv('训练曲线.csv',[dict(iteration=i+1,secure_loss=q['loss'],
        online_seconds=q['seconds'],online_wire_bytes=q['wire_bytes'],
        float_reference_loss=train['curves'][i]['float_loss'],
        fixed_reference_loss=train['curves'][i]['fixed_loss'],
        float_validation_accuracy=train['curves'][i]['float_validation_accuracy'],
        fixed_validation_accuracy=train['curves'][i]['fixed_validation_accuracy']) for i,q in enumerate(steps)])
    plot('训练损失.svg','密态训练损失与明文参考','Cora 诱导子图 64 节点；160 次真实密态更新；损失定义与数值语义见表',
         [('密态定点','#0d6173',[(i+1,q['loss']) for i,q in enumerate(steps)]),
          ('明文浮点参考','#cb692b',[(i+1,q['float_loss']) for i,q in enumerate(train['curves'][:160])])],
         '训练轮次','平均损失')
    publication=dict(status='REUSED_ACCEPTED_PUBLICATION',checkpoint_iteration=160,
                     source_parameter_count=3348,model_id=summary['model_id'],
                     m12_fraction_bits=12,m7_fraction_bits=7,
                     online_seconds=summary['publication']['online']['wall_seconds'],
                     online_wire_bytes=summary['publication']['online']['wire_bytes'],
                     online_rounds=summary['publication']['online']['rounds'],
                     offline_seconds=summary['publication']['offline']['offline_wall_seconds'],
                     checkpoint_binding_verified=summary['checkpoint_binding_verified'],
                     trace_bitwise_verified=summary['all_diagnostic_states_bitwise'],
                     published_test_accuracy=published['test']['accuracy'],
                     parameter_error_measured='UNAVAILABLE_TO_UNPRIVILEGED_REPORTER',
                     conversion_rule='signed floor(q12/32) mod 2^32; no floating rounding; max theoretical absolute real error <1/128, not an empirical maximum')
    comparisons=[]
    for route in ('legacy_ciphertext','private_decryption'):
        item=latest(f'he-{route}-64x6-ddefault-no-trace-*.json')
        if item:comparisons.append(item)
    aggregation=[]
    for degree in (2,4,8,16):
        for route in ('he','shared'):
            item=latest(f'aggregation-{route}-n64-c1-d{degree}*.json')
            if item:aggregation.append(item)
    if aggregation:
        write_csv('聚合节点度.csv',[dict(平均节点度=x['average_degree'],route=x['route'],
            nodes=x['nodes'],columns=x['columns'],operation_count=x['operation_count'],
            online_seconds=x['online_wall_seconds'],online_wire_bytes=x['online_wire_bytes'],
            online_rounds=x['online_rounds']) for x in aggregation])
        plot('节点度与聚合时间.svg','节点度与安全聚合时间','固定 64 节点、1 列、BFV 参数；每点为一次独立会话，HE 与共享密集矩阵均逐值通过',
             [('密文多项式','#0d6173',[(x['average_degree'],x['online_wall_seconds']) for x in aggregation if x['route']=='he_private_decryption']),
              ('共享密集矩阵','#cb692b',[(x['average_degree'],x['online_wall_seconds']) for x in aggregation if x['route']=='shared_dense'])],
             '平均非自环节点度','在线时间（秒）')
    activations=[x for width in (10,32) if (x:=latest(f'activation-k{width}-n32*.json'))]
    for item in activations:
        if 'public_test_vector' not in item:
            base=ROOT/'build/final-experiments/runtime/build/stage2'/item['session']
            shares=[read(base/f'S{role}/input.json')['operations'][0]['x'] for role in (0,1)]
            values=[(a+b)%(1<<32) for a,b in zip(*shares)]
            item['public_test_vector']=[v if v<1<<31 else v-(1<<32) for v in values]
    if len(activations)==2 and activations[0]['public_test_vector']!=activations[1]['public_test_vector']:
        raise RuntimeError('activation comparison used different input vectors')
    if activations:write_csv('激活位宽.csv',[dict(比较位宽=x['comparison_width_bits'],count=x['count'],
        keygen_seconds=x['keygen_seconds'],key_bytes_total=sum(x['fss_key_bytes_per_role']),
        online_seconds=x['online_worker_seconds'],online_wire_bytes=x['online_wire_bytes'],
        online_rounds=x['online_rounds']) for x in activations])
    scale=[x for n in (64,100,200,500,1000) if (x:=latest(f'he-private_decryption-{n}x1-ddefault-no-trace-*.json'))]
    if scale:
        write_csv('单层规模.csv',[dict(nodes=x['nodes'],columns=x['columns'],
            online_seconds=x['online_wall_seconds'],online_wire_bytes=x['online_wire_bytes'],
            online_rounds=x['online_rounds'],offline_seconds=x['offline_seconds']) for x in scale])
        plot('单层聚合规模.svg','单层同态聚合规模实验','固定 BFV 8192 度、1 列；合成图；不代表完整模型推理',
             [('受保护转换','#0d6173',[(x['nodes'],x['online_wall_seconds']) for x in scale])],
             '节点数','在线时间（秒）')
    full=next(q for q in summary['queries'] if q['route']=='he' and q['activation']=='fss')
    accepted_query=next(q for q in read(source/'acceptance.json')['queries']
                        if q.get('session')==full['request'])
    operations=accepted_query['online']['servers']
    component_costs=[]
    for index,stage in enumerate(operations[0]['operations']):
        for component in stage['components']:
            name=component['name']
            paired=[next(c for c in role['operations'][index]['components'] if c['name']==name)
                    for role in operations]
            component_costs.append(dict(operation=index,stage=stage['type'],name=name,
                max_role_seconds=max(c['elapsed_seconds'] for c in paired),
                bytes_sent=sum(c['bytes_sent'] for c in paired),rounds=component['rounds'],
                nested_in_parent=name=='private_BFV_round'))
    inference=dict(status='REUSED_ACCEPTED_FULL_64_NODE_QUERY',dataset='Cora induced 64 nodes',
                   test_count=published['test']['count'],secure_test_accuracy=published['test']['accuracy'],
                   online_seconds=full['online_wall_seconds'],online_wire_bytes=full['online_bytes'],
                   online_rounds=full['online_rounds'],offline_seconds=full['offline_seconds'],
                   stages=full['phases'],components=component_costs,
                   he_native_profiles=full['he_details'],
                   functionality_screenshot='results/local-page/connected-success.png',
                   external_baseline='UNMEASURED_SAME_WORKLOAD',
                   latency_speedup_vs_external=None,communication_reduction_vs_external=None)
    if len(comparisons)==2:
        ordered={x['conversion']:x for x in comparisons};legacy=ordered['legacy_ciphertext'];secure=ordered['private_decryption']
        inference['small_performance_path_comparison']=dict(nodes=64,columns=6,
            legacy_online_seconds=legacy['online_wall_seconds'],legacy_online_wire_bytes=legacy['online_wire_bytes'],legacy_rounds=legacy['online_rounds'],
            protected_online_seconds=secure['online_wall_seconds'],protected_online_wire_bytes=secure['online_wire_bytes'],protected_rounds=secure['online_rounds'],
            latency_ratio=secure['online_wall_seconds']/legacy['online_wall_seconds'],
            communication_ratio=secure['online_wire_bytes']/legacy['online_wire_bytes'],
            conditions='one HE aggregation layer, synthetic fixture, legacy ciphertext-view limitation; not full inference or external baseline')
    trace_run=latest('he-private_decryption-64x6-ddefault-trace-*.json')
    trace_allocated=None;trace_files=None
    if trace_run:
        folder=ROOT/'build/final-experiments/runtime/build/stage3'/trace_run['session']
        traces=list(folder.glob('S*/trace/*.ct'))
        trace_files=len(traces)
        trace_allocated=sum(p.stat().st_blocks*512 for p in traces)
    extract_times=[max(profile['extract_trace_seconds'] for profile in layer['roles'][0]+layer['roles'][1])
                   for layer in full['he_details']]
    conversion_times=[max(profile['conversion_seconds'] for profile in layer['roles'][0]+layer['roles'][1])
                      for layer in full['he_details']]
    performance_findings=dict(full_inference_he_stage_wire_bytes=sum(full['phases'][i]['bytes_sent'] for i in (1,3)),
        full_inference_he_stage_seconds=sum(full['phases'][i]['max_role_seconds'] for i in (1,3)),
        he_extract_seconds_per_layer=extract_times,
        protected_conversion_seconds_per_layer=conversion_times,
        optional_trace_files=trace_files,optional_trace_allocated_bytes=trace_allocated,
        trace_timing_comparison='NOT_VALID_FOR_SPEEDUP: trace run overlapped a 1000-node scale run; only disk blocks/count and both oracle checks are comparable',
        optimization_targets=['Galois-key constant-term extraction','protected BFV-to-share conversion and exact rounding',
                              'first-layer shared feature transform','probability circuit','FSS range-check cost'])
    same160_drop_pp=(float160['test']['accuracy']-published['test']['accuracy'])*100 if float160 else None
    result=dict(status='PARTIAL_MEASURED_CHAPTER5',
        groups={'1_training':training,'2_publication':publication,'3_aggregation':aggregation,
                '4_activation':activations,'5_inference':inference,'6_scale':scale},
        performance_findings=performance_findings,
        goals={'accuracy_drop_le_1pp_64_node':'MEASURED_ON_THIS_64_NODE_SAME_160_CHECKPOINT_PAIR' if same160_drop_pp is not None and same160_drop_pp<=1 else 'NOT_ESTABLISHED',
               'same160_accuracy_drop_percentage_points':same160_drop_pp,
               'degree_independent_core_count':'MEASURED_64_NODE_2_4_8_16' if len(aggregation)==8 else 'INCOMPLETE',
               'external_20x_latency':'MISSING_COMPARABLE_BASELINE',
               'external_400x_communication':'MISSING_COMPARABLE_BASELINE',
               'three_real_datasets_1000_full_queries':'NOT_MEASURED',
               'scope':'Experimental data shall not be interpreted as full-dataset accuracy or active security'})
    (OUT/'summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    lines=['# 第五章实验结果（事实口径）','',
      '本页从保留的真实记录生成。当前发布模型只覆盖 Cora 标签分层抽样后的 64 节点、551-6-7 两层网络；训练、验证、测试分别为 28、14、22 例。模型、种子和测试集未按本轮结果重选。',
      '', '## 1. 密态训练','',
      f'160 次真实密态更新：在线 {fmt(training["training_online_seconds"],1)} 秒、{training["training_online_wire_bytes"]:,} 字节；离线 {fmt(training["training_offline_seconds"],1)} 秒。首末密态损失 {fmt(training["initial_secure_loss"],4)} → {fmt(training["final_secure_loss"],4)}。',
      f'已发布模型测试准确率 {fmt(published["test"]["accuracy"]*100,2)}%，宏 F1 {fmt(published["test"]["macro_f1"]*100,2)}%；原选定 320 轮浮点参考测试准确率 {fmt(train["float_test_accuracy"]*100,2)}%。这两者训练轮数不同。',
      f'同图、同初始化、同 160 轮的已有浮点检查点事后只读评估：测试准确率 {fmt(float160["test"]["accuracy"]*100,2) if float160 else "不可用"}%，宏 F1 {fmt(float160["test"]["macro_f1"]*100,2) if float160 else "不可用"}%；该事后检查未用于挑选模型。',
      '在这 22 个测试节点上，一例分类变化对应约 4.55 个百分点。因此“下降不超过 1 个百分点”仅能表述为该小样本上观察到未下降，不能据此推断完整数据集或统计置信度。',
      '', '## 2. 模型发布','',
      f'3348 个参数从 12 位小数精度经秘密份额协议按有符号向下取整除以 32，刷新成 7 位模型；模型 ID `{publication["model_id"]}`。发布在线 {fmt(publication["online_seconds"])} 秒、{publication["online_wire_bytes"]:,} 字节、{publication["online_rounds"]} 轮；离线 {fmt(publication["offline_seconds"])} 秒。检查点绑定和四条推理轨迹逐位一致已由既有验收记录证明。',
      '现有本机普通身份无权读取迁移后的双方模型份额，故本轮未取得经验权重转换最大误差；按实现规则理论误差小于 1/128。这个理论上界不能写成实际测量值。',
      '', '## 3. 图聚合与节点度','',
      '| 平均度 | 同态在线秒 | 同态通信字节 | 密集共享在线秒 | 密集共享通信字节 |',
      '|---:|---:|---:|---:|---:|']
    for degree in (2,4,8,16):
        pair={x['route']:x for x in aggregation if x['average_degree']==degree}
        h=pair.get('he_private_decryption');s=pair.get('shared_dense')
        lines.append(f'| {degree} | {fmt(h["online_wall_seconds"] if h else None)} | {h["online_wire_bytes"] if h else "—"} | {fmt(s["online_wall_seconds"] if s else None)} | {s["online_wire_bytes"] if s else "—"} |')
    lines.extend(['', '同态每次执行 64 次行多项式乘法/常数项提取，固定 1 列；核心次数与四档节点度无关。密集共享对照每次执行 4096 个乘法，两个方案都逐值通过同一定点明文检查。行密文准备及离线材料不计在线通信；同态方案在本机这一规模仍更慢、通信更多。本表的对照是原工程共享密集矩阵路径，不是逐邻居秘密索引路径；逐邻居同条件实测仍缺失。',
      '', '## 4. 安全激活','',
      '| 比较位宽 | FSS 双方密钥字节 | 密钥生成秒 | 在线秒 | 在线字节 | 在线轮次 |',
      '|---:|---:|---:|---:|---:|---:|'])
    for x in activations:lines.append(f'| {x["comparison_width_bits"]} | {sum(x["fss_key_bytes_per_role"])} | {fmt(x["keygen_seconds"],4)} | {fmt(x["online_worker_seconds"],4)} | {x["online_wire_bytes"]} | {x["online_rounds"]} |')
    lines.extend(['', '同一批 32 个输入在两档均正确。10 位密钥更小、FSS 本体求值更快；其在线范围检查使本次总耗时与通信反而增加。密钥仅生成并写入离线私有文件，网络分发成本未实测。',
      '', '## 5. 完整推理','',
      f'既有实际发布模型、64 节点两层推理：测试准确率 {fmt(inference["secure_test_accuracy"]*100,2)}%；一次 HE + FSS 查询在线 {fmt(inference["online_seconds"])} 秒、{inference["online_wire_bytes"]:,} 字节、{inference["online_rounds"]} 轮；离线 {fmt(inference["offline_seconds"])} 秒。分阶段耗时/通信保存在 `results/chapter5/summary.json` 和原始 `results/application/.../summary.json`。',
      '测试集准确率由独立验证端核对全图输出；真实线上接收端只恢复固定授权目标的最终概率，不接收完整测试预测。',
      '尚无同工作负载、相同设备及网络的外部安全图推理实现实测；20 倍时延与 400 倍通信目标均为“缺少可比基线，无法判断”，不可用文献数字或单层旧路径代替。'])
    lines.append('实际分阶段组件记录包括特征变换、图聚合、BFV 转换、范围检查、FSS 激活、截断和概率计算。`private_BFV_round` 是转换组件的内部部分，不能与父组件重复相加；见机器结果 `groups.5_inference.components`。既有真实页面截图：`results/local-page/connected-success.png`。')
    if comparisons:
        lines.append('隔离性能路径实测（64 节点、6 列、单层）：'+', '.join(
          f'{x["conversion"]} {fmt(x["online_wall_seconds"])} 秒/{x["online_wire_bytes"]:,} 字节/{x["online_rounds"]} 轮' for x in comparisons)+'。旧路径有已知密文视图限制，不作为正式受保护服务结果。')
    lines.extend(['', '## 性能定位与尚未达标的原因', '',
      f'既有完整查询的两层 HE 聚合阶段合计 {performance_findings["full_inference_he_stage_wire_bytes"]:,} 字节、约 {fmt(performance_findings["full_inference_he_stage_seconds"])} 秒（各阶段较慢角色耗时相加）；原生常数项提取分别约 {fmt(extract_times[0])} 与 {fmt(extract_times[1])} 秒，受保护转换分别约 {fmt(conversion_times[0])} 与 {fmt(conversion_times[1])} 秒。全链还包括首层共享特征变换与概率电路，见分阶段机器记录。',
      f'可选无诊断轨迹模式在一次 64 节点、6 列、双方会话中避免写入 {trace_files if trace_files is not None else "未知"} 个中间密文文件，按文件分配块计 {trace_allocated if trace_allocated is not None else "未知"} 字节；必需掩码密文仍保留。该有轨迹时延样本与 1000 节点实验重叠运行，不据其计算加速比。',
      '后续优先定位常数项 Galois 提取与 BFV 密文到份额转换，再分析首层特征变换、概率电路及 FSS 范围检查。当前代码没有给出同条件外部系统实测，因此 20 倍与 400 倍均不可判断。',
      '现有发布模型及预处理图严格绑定 64 节点。1000 节点单层实验只证明同态聚合子程序容量；要完成三套真实图的 1000 节点两层分类，还需真实数据、匹配模型、范围预算与全链材料/时间预算。',
      ''])
    lines.extend(['', '## 6. 规模扩展','',
      '| 节点数 | 单层 HE 在线秒 | 在线字节 | 状态 |',
      '|---:|---:|---:|---|'])
    for n in (100,200,500,1000):
        row=next((x for x in scale if x['nodes']==n),None)
        lines.append(f'| {n} | {fmt(row["online_wall_seconds"] if row else None)} | {row["online_wire_bytes"] if row else "—"} | {"单层合成图实测通过" if row else "待测"} |')
    lines.extend(['', '这些是单层合成图容量/成本实验，不含已发布 64 节点模型、真实标签或完整两层概率推理。现有模型与输入绑定 64 节点，扩展完整真实图还需新数据、模型及范围预算，不能仅改入口限制。',
      '', '## 图表与口径','',
      '矢量图：[训练损失](../public/chapter5/训练损失.svg)、[节点度与聚合时间](../public/chapter5/节点度与聚合时间.svg)、[单层聚合规模](../public/chapter5/单层聚合规模.svg)。[公开汇总 JSON](../public/chapter5/summary.json) 与 CSV 同目录；完整单会话原始记录保留在本机 `results/final-experiments/`。图表只使用保留的真实记录，可不重跑协议重新渲染。',
      '在线通信计双向发送字节与协议帧；轮次为成对交换。离线生成、HE 图行加密、模型迁移与接收端导出另列，不混入在线。单次本机时延不是稳定跨系统加速比。',
      '本机两方半诚实、可信离线方及管理员边界继续有效；旧转换的额外安全性质未获证明。'])
    (ROOT/'docs/chapter5-results.md').write_text('\n'.join(lines)+'\n')
    (ROOT/'docs/chapter5-status.json').write_text(json.dumps(result['goals'],ensure_ascii=False,indent=2)+'\n')
    public=ROOT/'public/chapter5';public.mkdir(parents=True,exist_ok=True)
    for source_file in sorted(OUT.iterdir()):
        if source_file.is_file() and source_file.suffix in ('.json','.csv','.svg'):
            shutil.copyfile(source_file,public/source_file.name)
    print(json.dumps(dict(status=result['status'],groups={k:(len(v) if isinstance(v,list) else v['status'])
        for k,v in result['groups'].items()},output=str(OUT)),ensure_ascii=False))

if __name__=='__main__':main()
