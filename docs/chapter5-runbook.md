# 第五章实验运行与复核

当前已验收的发布模型是 Cora 诱导子图 64 节点、两层 551-6-7 网络。第五章脚本复用原工程的 `src.offline`、`src.mpc_worker`、`src.runtime`、`src.he`、`src.storage` 和同一份 `config/phase0.json`。新协议实验在 `build/final-experiments/runtime` 内使用独立会话、账本、材料与同一套代码/SEAL 二进制；不会读取或改写本机部署的 `/var/lib/privacy-gnn` 账本。

先运行已完成结果的只读汇总：

```bash
cd /home/tenggn/projects/privacy_gnn
python3 scripts/final_experiments.py --group all
python3 verification/final_experiment_checks.py
```

需要补测时，按组执行：

```bash
python3 scripts/final_experiments.py --group 3 --dataset Cora --nodes 64 --repeat 1 --execute
python3 scripts/final_experiments.py --group 4 --dataset Cora --nodes 64 --repeat 1 --execute
python3 scripts/final_experiments.py --group 6 --dataset Cora --nodes 64 --scale-nodes 100 200 500 1000 --repeat 1 --execute
```

总入口 `--group all --execute` 顺序执行缺失的短实验。成功的会话默认跳过；确需重复测量时显式传 `--force-new-sessions`，它只创建新会话，绝不恢复或复用旧材料。`--repeat` 限制为 1–5。每次请求在 `results/final-experiments/dispatch-*.json` 记录当前 Git 提交、工作区 diff 摘要、涉及的源码哈希、统一配置哈希、CPU、系统、空间探针、命令结果和失败原因。原始各会话 JSON 不覆盖；失败保留独立 `.failed.json`，下次运行只补缺项。脚本结束自动调用 `scripts/report_chapter5.py`，仅从已保存原始结果生成中文 Markdown、CSV 与 SVG；可单独运行该渲染脚本调整排版，不重跑密码协议。

| 组别 | 入口与实际范围 | 当前验收依据 |
|---|---|---|
| 1 训练 | 总入口只读，复用 160 次真实更新与已有浮点检查点；从保留的 160 轮浮点权重只读计算同预算测试指标 | 原 `results/application/a49152b33097752eaf81a7cba6d910a3/`、`results/representative/` |
| 2 发布 | 总入口只读，复用检查点绑定、模型发布与四条同模型轨迹 | 原应用验收报告；普通身份无权直接查看已迁移双方模型份额 |
| 3 聚合 | `verification/final_aggregate.py`，固定 64 节点/1 列，平均度 2/4/8/16；同态行编码对共享密集矩阵；同条件明文定点逐值核对 | 新独立会话原始 JSON |
| 4 激活 | `verification/final_activation.py`，同一批 32 输入，比较位宽 10 和 32；核对结果、FSS 密钥生成、序列化长度与在线成本 | 新独立会话原始 JSON |
| 5 完整推理 | 总入口只读复用已通过的 64 节点真实发布模型查询及阶段记录；浏览器功能截图使用已有成功记录 | 原应用验收与 `results/local-page/connected-success.png` |
| 6 规模 | `verification/final_he_compare.py`，单层合成图 100/200/500/1000 节点，固定 BFV 8192 度、1 列，逐值核对 | 新独立会话原始 JSON；不表示 1000 节点完整两层推理 |

低交互路径独立对照：

```bash
python3 verification/final_he_compare.py --conversion both --nodes 64 --columns 6 --no-trace
```

它分别使用现有 `legacy_ciphertext` 与 `private_decryption`，密文聚合及定点输入相同。旧路径的密文视图限制仍在；它的较低通信量不是当前正式受保护服务的安全结论。`--no-trace` 只省略每行乘法/提取和每列打包的**诊断密文落盘**，会继续保存必须发送的掩码密文；验收时不带此开关仍可保留完整诊断轨迹。所有协议会话先检查宿主和子系统余量，离线方按已存在的准入/材料作废语义工作。纯展示汇总不会生成材料。

第五章结果位于 `docs/chapter5-results.md` 和 `results/chapter5/`。报告写作时要保留以下边界：标签参与 64 节点分层抽样；浮点 320 轮与密态 160 轮是不同训练预算；同 160 轮的浮点指标为事后诊断，不能反向选择模型。`results/chapter5/summary.json` 的阶段组件有父子嵌套，不可直接相加。FSS 密钥在本机离线生成后写入角色材料文件，网络分发开销尚未实测。外部同工作负载/硬件/网络的安全 GNN 基线尚未实测，因此不能宣称 20 倍或 400 倍达标。

`public/chapter5/` 是上述允许公开的统计、CSV 和矢量图的 Git 版本快照；角色输入、模型份额、密钥、材料、账本和原始运行目录仍只保存在本机。完整单会话计时 JSON 保留在 `results/final-experiments/`，审阅包另行列明哈希，不让网页进程接触运行目录。

`python3 scripts/build_chapter5_evidence.py` 生成 `review/chapter5-evidence.tar.gz` 与逐文件 SHA-256 清单，只纳入通过的公开计时 JSON、汇总图表、说明文档和既有真实页面成功截图；不打包隔离目录中的输入份额、密钥或消费账本。

外部比较的候选来源可从 [SecGNN 原论文](https://arxiv.org/abs/2202.07835) 与 [CoGNN 作者仓库](https://github.com/InspiringGroup-Lab/CoGNN) 开始。两者公开任务/威胁边界和本工程不自动等价；本轮没有取得可在相同 64 节点或 1000 节点工作负载、本机 CPU/网络、同一在线通信计数口径下复现的运行结果。因此文献数字不录入加速倍数表。

运行前可检查 `python3 -c 'from src.storage import snapshot; print(snapshot("."))'`。宿主空间探针失败时，新材料准入应拒绝。无需 `sudo`；新实验在用户拥有的隔离目录运行。若受执行沙箱限制而出现子进程 `socket` 权限错误，保留失败材料并在正常本地终端用新会话运行，不能继续旧会话。
