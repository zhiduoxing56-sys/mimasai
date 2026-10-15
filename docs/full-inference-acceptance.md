# 发布模型完整双层推理验收

此入口只使用既有 64 节点、160 轮共享训练后发布的模型 `829a29a6913d505e7167f418a94674ee` 和固定授权目标 936。不会重新训练或扩大图。两个请求各自生成新离线材料；首次必须执行两层并在完整交付后建立首层缓存，第二次必须从角色私有缓存读取隐藏份额，继续执行第二层、秘密概率和最终授权交付。已接受的独立定点参考来自 `verification/application.py` 的 `published_reference`、`verify_queries` 及 `results/application/a49152b33097752eaf81a7cba6d910a3/acceptance.json`。本次操作入口只读取该验收记录，不读取双方私有目录。

## 冻结部署及验收顺序

部署前应保持工作区干净，检查 `git rev-parse HEAD`、`build/he_bridge-build.json` 与 `build/he_bridge` 的摘要。管理员在本机终端执行：

```bash
cd /home/tenggn/projects/privacy_gnn
sudo --preserve-env=WSL_DISTRO_NAME /usr/bin/python3 scripts/install_local_roles.py --check
sudo --preserve-env=WSL_DISTRO_NAME /usr/bin/python3 scripts/install_local_roles.py --install
sudo --preserve-env=WSL_DISTRO_NAME /usr/bin/python3 scripts/install_local_roles.py --verify
python3 scripts/local_deployment.py audit
```

管理员密码只在本机终端输入。安装器保留旧原生二进制发布和既有状态；冻结服务源码摘要及原生二进制摘要必须与工作区一致。审计通过后执行：

```bash
python3 scripts/accept_full_inference.py
```

入口在发起请求前验证冻结源码、原生二进制、六身份权限验收及首层缓存为空。每个请求经真实回环页面 API 提交，记录阶段、授权最终概率、在线双向发送字节、轮数、各操作成本、离线耗时、清理空间口径和材料独立性。首次请求必须完整交付、清理并安装缓存；第二次必须由首次会话的缓存进入。若任一步失败，已有材料永久作废，入口停止且不自动重试。验收记录位于 `results/chapter5/full-query-acceptance.json`，单请求原始证据位于 `results/local-page/query-attempt-<会话>.json`。重复执行已通过入口只返回已有结果。

## 既有可比基线

既有验收会话 `7a4cda63efe0fc5b06c4a45aa9af3e32` 使用同一发布模型、64 节点图、目标 936、两层 HE/FSS 路径。在线 35.76137758 秒、双方发送 96,792,628 字节、1306 轮；离线 50.627578168 秒。各阶段成本由既有服务器操作记录提取。此前真实页面查询 `results/local-page/query-attempt-3b51037357e803f5ad868c26534bb568.json` 的在线成本为 35.780439903 秒、96,792,628 字节、1306 轮，可作为旧版冻结服务的交叉核对。完整端到端页面时间含离线、输入、导出及清理，不与在线时间混算。

新增的两个真实请求尚未完成时，不计算“新版加速倍数”。首层缓存准备成本属于首次请求，不摊入第二次在线时间；第二次仍需新离线材料。阶段墙钟按同时运行的两个角色较大值记录，阶段合计不等同于完整后端墙钟；各阶段的双方发送字节可以相加，但握手等操作外成本单列于在线总量。所有数值语义和授权边界沿用冻结模型。

## 扩展及外部对照

1000 目标节点需要新的图、模型输入绑定、节点顺序、HE 资产和成本评估；目前正式入口仅允许 16、32、64 节点，64 节点模型不能直接声明支持 1000 节点。应待本页两次完整实测通过后才规划容量修改和完整实验。

Panther 官方实现采用四方计算并提供 Cora 等数据准备与本机/LAN/WAN 运行入口：<https://github.com/CHEN-CONGCONG/Panther>。其公开论文为 <https://arxiv.org/abs/2511.01654>。协议参与方、图/模型预处理及测量口径与本系统不同；尚未在同一硬件、网络、模型、节点规模和查询口径下复测，因此本项目目前没有可用于断言 20 倍时延或 400 倍通信指标的 Panther 对照数值。
