# 在线性能工程短测与部署边界

本次改动基于已发布的 64 节点、160 轮共享训练模型接口，未重训、扩图、恢复模型或修改定点数值语义。公开机器可读汇总见 [`public/chapter5/performance-engineering.json`](../public/chapter5/performance-engineering.json)。以下各项为**部署前的隔离实验结果**；后续已完成新版冻结服务两次真实完整查询，实际成绩见[完整推理实测](full-inference-results.md)。不要将下列单层短测当作完整推理成本。

| 改动与条件 | 旧实现 | 新源码隔离短测 | 正确性范围 |
|---|---:|---:|---|
| 受保护 HE 单层，64 节点×6 列，在线耗时 | 11.950 秒 | 6.748 秒 | 逐项等于同条件固定点结果 |
| 同上，双方在线通信 | 30.739 MB | 8.196 MB | 仍不向对方发送被求值密文或明文相位 |
| 同上，交互轮数 | 65 | 55 | 新材料、独立会话 |
| 概率电路，64 行×7 类、f12，轮数 | 729 | 541 | 448 个概率单位逐项等于既有固定点参考 |
| 同形概率电路，双方通信 | 8.891 MB | 1.046 MB | 旧值取自已验收 HE/FSS 完整查询，新值为合成输入独立电路 |
| 截断加缩减位宽范围检查，5 个值 | 72 轮 | 41 轮 | 有效值相同，越界仍拒绝 |

HE 对照的旧值来自保留的无轨迹单层测试，新值来自新会话；测得单层在线加速约 1.77 倍、通信缩减约 3.75 倍。正式查询计划现也关闭逐节点调试密文落盘，保留最终发送密文和必要指标。C++ 将每列各节点的同一常数项投影并行执行，仍按节点顺序重新打包。旧指标的提取串行时间为 7.416 秒；新日志记录并行投影区域 2.783 秒，但该新区域还含并行明文乘法，故更稳妥的对比是完整 native 评价 7.852→2.866 秒。重打包仅约 0.04–0.05 秒，继续改写它对总成本收益很小。并行上限为 4 个工作线程，伽罗瓦变换与密钥切换的总次数尚未降低；批量密钥切换仍是下一步研究点。

受保护 BFV 转换仍由可信离线方准备环 Beaver 三元组，两台在线方保留私有密钥／密文分离。一个密钥组内使用同一个随机 `b`，每列保留独立随机 `a` 与对应的 `c=a·b`；在线仅打开一次公共的 `e=s-b`，批量交换各列的 `d=c₁-a`。组与材料标识都绑定到单次会话，跨组、跨请求不复用。单独加入分组、尚未位打包时，64×6 通信 30.739→26.802 MB，轮数 65→55；其余降至 8.196 MB 的通信收益主要来自布尔消息位打包。新线格式带版本标识，低位优先，接收端检查末字节填充位；这也降低了 BFV 精确舍入、范围检查和概率计算通信。旧低交互转换只用于性能参照，没有切换回旧的密文视图路径。

首层状态采用两台服务器分别持有的缓存。首次**成功完成完整交付**的请求，在受限角色内部把第一层 FSS 激活后的隐藏份额写入各自秘密资产，并在双方安装成功后由管理员侧持久登记公开绑定标记。后续请求才跳过 `XW₀ → HE 聚合 → 激活`，从本方隐藏份额开始第二层运算，并为剩余操作生成全新一次性材料。读取时重新核对模型、输入份额、HE 图资产和会话绑定；发生改变就拒绝旧缓存。协调器只收到绑定与安装状态，不接触隐藏份额。当前实现是**首次成功请求后缓存**，尚无独立预热命令，因此首个请求仍承担首层计算。现有公开 64 节点模型的保守磁盘准入预算从完整计划约 1.647 GB 降至缓存计划约 0.818 GB；这是预算上界，不是实际占用或回收量。7 节点×6 列隔离测试验证了跨新会话 42 个隐藏值逐项一致和源资产改变拒绝；它不是现有发布模型的完整页面查询。

概率归一化仍使用原有 `T₂` 多项式、逐次向下截断和精确无符号除法。七类最大值改为分层批量比较，最大值数学结果不变。由于最大类的指数精确为 `S`，分母至少为 `S`，长除法开头 12 个高位商必为零；新代码从该前缀余数继续原精确除法。范围守卫没有关闭。激活前的 HE 截断已产生秘密二进制位，范围检查现在复用截断后的保留位，而不再次分解同一数值；仍只公开原先允许的整批范围通过位，越界会停止并永久作废材料。5 个值的对照及拒绝测试和 7 节点 HE/FSS 实测均通过。

受影响验证命令：

```bash
python3 verification/bitpacked_channel.py
python3 verification/fused_range.py
python3 verification/hidden_cache_reuse.py
python3 verification/probability_prefix.py --rows 64
python3 verification/final_he_compare.py --conversion private_decryption --nodes 64 --columns 6 --no-trace
python3 -m unittest verification.hidden_cache_deployment_checks verification.deployment_mode_checks verification.local_page_checks
python3 scripts/report_performance_engineering.py
```

涉及真实双进程、socket 与新随机材料的短测只在已有独立 `build/final-experiments/runtime` 中运行。已验收的 160 轮训练及发布检查点直接复用，未再跑训练。**后续部署验收**已在 2026-10-15 完成：管理员安装、六身份 140 项权限审计，以及两次新材料完整推理；见[完整推理实测](full-inference-results.md)。20 倍时延及 400 倍通信目标仍缺少同工作负载外部基线，不能按内部优化倍数认定达标。本机角色隔离只属于部署保障；两方半诚实、可信离线方及管理员边界保持不变。

本轮同时修正了安装器原先“native 二进制存在就不更新”的断点。编译脚本会写入源码、脚本、二进制摘要；安装前检查三者一致。管理员安装在停止服务后把新二进制原子换版，将旧二进制保留在只读版本目录，并在 `--verify` 比对实际安装摘要。以下为本轮**已经执行**的管理员安装命令，保留以便复核：

```bash
cd /home/tenggn/projects/privacy_gnn
sh scripts/build_stage3.sh
sudo --preserve-env=WSL_DISTRO_NAME /usr/bin/python3 scripts/install_local_roles.py --check && \
sudo --preserve-env=WSL_DISTRO_NAME /usr/bin/python3 scripts/install_local_roles.py --install && \
sudo --preserve-env=WSL_DISTRO_NAME /usr/bin/python3 scripts/install_local_roles.py --verify && \
python3 scripts/local_deployment.py audit
```

`--check`要求工作区已提交且干净、宿主空间可读、服务状态文件未被占用；`audit`完成更新后六个真实 UID 的权限复核。管理员密码只在本地终端输入。本轮两次完整请求已经证明首次缓存安装和下一请求实际跳过首层，详见[验收证据](full-inference-results.md)。
