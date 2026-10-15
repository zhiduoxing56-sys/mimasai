"""Regenerate public Chapter 5 table and vector figure from two accepted queries."""
import hashlib,json,math,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'results/chapter5/full-query-acceptance.json'
PUBLIC=ROOT/'public/chapter5/full-inference.json'
DOCUMENT=ROOT/'docs/full-inference-results.md'
FIGURE=ROOT/'public/chapter5/完整推理性能.svg'

def row(name,record):
    online=record['online']
    return dict(condition=name,session=record['session'],online_seconds=online['wall_seconds'],
                online_sent_bytes=online['wire_bytes'],online_rounds=online['rounds'],
                offline_seconds=record['offline_wall_seconds'],
                complete_request_seconds=record.get('total_request_wall_seconds'))

def xml(value):return str(value).replace('&','&amp;').replace('<','&lt;').replace('>','&gt;')
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def figure(rows):
    names=['优化前完整请求','优化后首次请求','优化后缓存命中']
    colors=['#65758b','#1b7892','#bd6845']
    out=['<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="570" viewBox="0 0 1200 570">',
         '<rect width="1200" height="570" fill="#f8fafc"/>',
         '<text x="62" y="55" font-family="Noto Sans CJK SC, sans-serif" font-size="27" font-weight="700" fill="#17233a">已发布模型完整双层推理：首次与缓存命中</text>',
         '<text x="62" y="82" font-family="Noto Sans CJK SC, sans-serif" font-size="15" fill="#536477">Cora 64 节点 · 551–6–7 · 授权目标 936 · 本机两方在线发送字节</text>']
    for top,title,key,unit,maximum in [(112,'在线墙钟','online_seconds','秒',40),(328,'在线通信','online_sent_bytes','MiB',105)]:
        out.append(f'<text x="62" y="{top}" font-family="Noto Sans CJK SC, sans-serif" font-size="19" font-weight="700" fill="#17233a">{title}</text>')
        for i,(name,r,color) in enumerate(zip(names,rows,colors)):
            y=top+30+i*54;value=r[key] if key=='online_seconds' else r[key]/2**20
            width=650*value/maximum
            out.append(f'<text x="62" y="{y+21}" font-family="Noto Sans CJK SC, sans-serif" font-size="15" fill="#23344b">{xml(name)}</text>')
            out.append(f'<rect x="260" y="{y}" width="650" height="29" rx="5" fill="#e5eaf0"/>')
            out.append(f'<rect x="260" y="{y}" width="{width:.2f}" height="29" rx="5" fill="{color}"/>')
            out.append(f'<text x="{275+width:.2f}" y="{y+21}" font-family="Noto Sans CJK SC, sans-serif" font-size="15" fill="#17233a">{value:.2f} {unit}</text>')
    out.append('<text x="62" y="553" font-family="Noto Sans CJK SC, sans-serif" font-size="13" fill="#536477">单次真实会话；离线材料生成、图与模型准备、导出不计入在线条形。首次请求承担首层缓存建立。</text>')
    return '\n'.join(out+['</svg>'])+'\n'

def main():
    data=json.loads(SOURCE.read_text());assert data['status']=='PASS_TWO_FULL_QUERIES' and len(data['requests'])==2
    old,cold,warm=data['baseline'],*data['requests']
    assert cold['condition']=='cold_full' and warm['condition']=='cache_hit'
    assert cold['reference_equal'] and warm['reference_equal'] and all(data['fresh_material'].values())
    rows=[row('优化前完整请求',old),row('优化后首次请求',cold),row('优化后缓存命中',warm)]
    assert all(math.isfinite(r['online_seconds']) and r['online_seconds']>0 for r in rows)
    phases=[]
    for record in (old,cold,warm):
        phases.append([dict(operation=s['operation'],type=s['type'],seconds=s['elapsed_seconds'],
                            sent_bytes=s['wire_bytes'],rounds=s['rounds']) for s in record['online']['stages']])
    permission_path=ROOT/'results/local-page/real-uid-permissions.json'
    permissions=json.loads(permission_path.read_text())
    attempts=[ROOT/'results/local-page'/('query-attempt-'+q['session']+'.json') for q in (cold,warm)]
    assert permissions['status']=='PASS_REAL_UID_MATRIX' and len(permissions['roles'])==6
    assert sum(len(r['checks']) for r in permissions['roles'])==140
    public=dict(status='PASS_TWO_FULL_REAL_PUBLISHED_MODEL_QUERIES',source_deployment=data['deployment'],
                model_id='829a29a6913d505e7167f418a94674ee',source_training_iteration=160,
                graph_nodes=64,model_dimensions=[551,6,7],authorized_target='936',
                reference_probability_units=data['expected_probability_units'],reference_fraction_bits=12,
                two_queries_match_independent_fixed_reference=True,first_layer_skipped_on_second=True,
                fresh_material=data['fresh_material'],rows=rows,stages=phases,ratios=data['ratios'],
                evidence_hashes=dict(full_query_acceptance_sha256=sha(SOURCE),real_uid_permissions_sha256=sha(permission_path),
                                     request_attempt_sha256=[sha(path) for path in attempts]),
                real_uid_audit=dict(status=permissions['status'],roles=6,checks=140),
                cleanup_observations=[{key:q['cleanup'][key] for key in ('deleted_file_allocated_bytes','unlinked_last_link_allocated_bytes',
                    'removed_files','reclaimable_upper_bytes','observed_internal_available_delta','observed_host_available_delta')}
                    for q in (cold,warm)],
                measurements='Single real session per condition; online wall excludes offline and delivery; both-direction sent bytes incl protocol framing; paired exchange rounds',
                limitations='Historical baseline on same published model and node, different frozen code; no repetitions or external same-workload baseline; 64-node stratified sampled graph only')
    PUBLIC.write_text(json.dumps(public,ensure_ascii=False,indent=2)+'\n')
    FIGURE.write_text(figure(rows))
    lines=['# 已发布模型完整双层推理实测','',
           '本页由 `scripts/report_full_inference.py` 从真实验收记录生成；原始记录为 `results/chapter5/full-query-acceptance.json`。',
           '三种条件均使用已验收的 64 节点、160 轮密态训练发布模型，固定授权目标 936；优化前为既有独立验收会话，优化后两次为本轮各自新材料的真实页面 API 请求。',
           '', '| 条件 | 在线秒 | 双方发送字节 | 轮数 | 离线秒 | 完整请求秒 |',
           '|---|---:|---:|---:|---:|---:|']
    for r in rows:
        total='—' if r['complete_request_seconds'] is None else f"{r['complete_request_seconds']:.3f}"
        lines.append(f"| {r['condition']} | {r['online_seconds']:.3f} | {r['online_sent_bytes']:,} | {r['online_rounds']} | {r['offline_seconds']:.3f} | {total} |")
    ratio=data['ratios']
    lines+=['',f"相对既有完整请求，首次在线时延改善 **{ratio['baseline_over_cold_wall']:.2f} 倍**、通信缩减 **{ratio['baseline_over_cold_wire']:.2f} 倍**；缓存命中分别为 **{ratio['baseline_over_warm_wall']:.2f} 倍**、**{ratio['baseline_over_warm_wire']:.2f} 倍**。",
            f"缓存命中相对本轮首次请求，在线时延改善 **{ratio['cold_over_warm_wall']:.2f} 倍**、通信缩减 **{ratio['cold_over_warm_wire']:.2f} 倍**。首次请求承担首层计算和缓存持久化，第二次仍重新生成一次性离线材料并执行第二层、秘密概率及授权交付。",
            '', '两次最终七类概率均逐项等于已验收独立定点参考：`[2944,58,20,938,25,67,40]/4096`；会话和材料批次不同，环材料及 HE 掩码标识无交集。完整交付后角色私有首层份额与模型、图、输入哈希和来源会话绑定；第二次操作记录从 `load_hidden` 开始，仍包含第二层 HE 聚合、概率电路和 `deliver`。',
            '', '![三种完整推理条件在线成本](../public/chapter5/完整推理性能.svg)',
            '', '## 分阶段在线成本',
            '', '| 条件 | 阶段序列：阶段类型 / 较慢角色耗时秒 / 双方发送字节 / 轮数 |',
            '|---|---|']
    for r,items in zip(rows,phases):
        line='；'.join(f"{s['type']} {s['seconds']:.3f}s / {s['sent_bytes']:,}B / {s['rounds']}轮" for s in items)
        lines.append(f"| {r['condition']} | {line} |")
    lines+=['', '阶段墙钟取同时执行的两个在线角色中较慢者，不能相加当作总墙钟；其中 `he_aggregate` 含 HE 聚合、受保护转换、截断和必要激活，内部嵌套组件不能重复相加。各阶段通信之和不含少量握手帧，总通信以上表为准。',
            '', '## 边界与解释',
            '', '在线成本与离线成本分别记录；首次请求的预热工作不摊入第二次在线成本。历史基线是同模型同图同目标的真实完整查询，但来自先前冻结版本；这里每个条件只有一次会话，数字不是稳定分布或跨系统成绩。旧版完整服务在线成本的另一次既有查询为 35.780 秒、96,792,628 字节、1306 轮，可交叉核对历史基线。',
            '清理记录分别保存删除文件分配块、末次硬链接分配块、内部可用空间变化和宿主可用空间变化；不会把可回收上界当作宿主实际回收。',
            '', '| 本轮清理 | 删除文件分配块 | 末次硬链接分配块 | 内部可用空间变化 | 宿主可用空间变化 |',
            '|---|---:|---:|---:|---:|']
    for r,q in zip(rows[1:],(cold,warm)):
        o=q['cleanup'];lines.append(f"| {r['condition']} | {o['deleted_file_allocated_bytes']:,} | {o['unlinked_last_link_allocated_bytes']:,} | {o['observed_internal_available_delta']:,} | {o['observed_host_available_delta']:,} |")
    lines += ['',
            'Panther 官方实现使用四方计算，尚未在相同工作负载、设备及网络下复测。因此 20 倍在线时延和 400 倍在线通信量目标仍为“缺少可比外部基线，无法判断”，不能用本表内部优化倍数替代。',
            '本机六身份隔离只属于部署保障；两方半诚实、可信离线方、管理员边界和 64 节点分层抽样范围保持不变。','']
    DOCUMENT.write_text('\n'.join(lines))
    print(json.dumps(dict(status=public['status'],public=str(PUBLIC),document=str(DOCUMENT),figure=str(FIGURE)),ensure_ascii=False))

if __name__=='__main__':main()
