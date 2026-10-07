最新交付（2026-10-08）：三页中文演示界面已完成，见[启动说明与3—5分钟演示稿](docs/demo-runbook.md)、[逐项验收清单](docs/demo-final-acceptance.md)。7项受影响短测及独立浏览器检查通过；既有真实查询与六身份140项证据保留复用，新密码查询为零。**新版待管理员冻结部署，现有真实服务仍为e7e5436。** 预览明确未连接，不生成示例预测；部署命令、五张截图、三页离线HTML和新版审阅包已交付。以下2026-10-07完成项是旧冻结版本的真实验收记录。

新增交付（2026-10-07，冻结运行版本 e7e5436）：[本机页面与部署验收](docs/local-page-acceptance.md)、[管理员部署步骤](docs/local-admin-deployment.md)。六真实身份140项检查通过，账本与原发布资产保持inode。真实页面HTTP接口查询完整交付：目标936，Case_Based概率71.875%，实际72.31秒、在线发送92.31 MiB。输入故障、独立新材料、重复提交、清理后重用拒绝及实际浏览器成功/失败/刷新均通过；没有新增管理员阻塞。源码包和公开证据包在review目录，能力令牌/cookie不打包。不重训、扩图、改变数值语义或历史批量删除。

本轮交付（2026-10-06，基线 c9840ed）：[停止与交付异常验收、权限矩阵及阻塞](docs/lifecycle-role-acceptance.md)、[本轮独立证据](docs/lifecycle-role-results.json)。已修复进程组后代停止、完整工作流异常收尾及清理观测；当时账户创建被sudo身份验证阻止，现已由上述部署完成身份及页面验收。既有模型与160轮训练结果保留，本轮不重训。

既有交付（2026-10-05）：[磁盘预算与保留政策](docs/disk-retention.md)、[结果解释与命令行验收](docs/storage-delivery-acceptance.md)、[聚合证据](docs/storage-delivery-results.json)。当时命令行演示复用既有64节点160轮发布模型，每次使用新材料，只由授权接收端恢复最终概率。历史清理仅交付预览，未删除。管理员迁移后的在线资产由真实角色管理，普通操作员不再直接运行旧`demo.py`读取私有目录；使用受限页面/接口，访问方法及真实查询证据见上述部署验收。

本轮真实64节点160轮共享训练与多类指标见[验收报告](docs/representative-acceptance.md)，抽样与训练概率f14见[实验说明](docs/representative-experiment.md)；旧64节点96轮回归保留。正式入口支持 `--sampling stratified_frontier --seed 20261005`，不外推到完整Cora。

# 图隐私计算工程

以下保留原数据/训练入口及历轮报告。本轮演示只复用现有64节点160轮发布模型，通过127.0.0.1:8765页面及受限角色接口查询。原真实Cora数据入口支持16、32和64节点诱导图，使用自有两层GCN、两进程共享训练、持续共享发布、受保护同态推理及秘密近似概率；历史完整运行命令：

```sh
sh scripts/run_application.sh --nodes 64 --sampling stratified_frontier --seed 20261005 --steps 160 --validate --faults
```

操作与权限见[应用运行说明](docs/application.md)，数据语义及许可缺口见[数据说明](docs/real-data.md)。仅向公开授权目标交付最终概率份额，由独立接收端恢复；本机半诚实与可信非串谋离线假设，不是主动安全或跨机认证部署。原低交互密文转换仍安全阻塞。实际验收证据见[本轮报告](docs/unattended-acceptance.md)。

以下保留历轮记录。

# 图隐私计算阶段零至阶段三第一轮

本仓库保存阶段零协议调查与阶段一浮点训练、定点前向及模型接口参考。已从用户提供的 Windows 路径读取比赛设计稿与 HyGNN 论文，并保留字节一致的项目内副本。原算法发现可复现错误；发布与数值转换仍有协议缺口。这里没有安全训练系统或完整推理服务。

运行独立参考验证：`sh scripts/run_reference.sh`。已有本地依赖时运行真实同态验证：`sh scripts/build_he.sh`。统一测试参数在 `config/phase0.json`；32 位环、7 位小数及同态模数链依据 HyGNN VII，阶段一参考图和模型语义按用户指定基线统一，32/7仅用于定点推理参考。入口逐项保存成功和失败，不能以脚本退出零认定所有参数都通过。

交付索引：

- [实现规格与材料对应表](docs/specification.md)
- [参与方与信任假设](docs/trust.md)
- [训练推理接口与数值规则](docs/interface.md)
- [问题与待确认事项](docs/issues.md)
- [依赖来源和构建记录](docs/dependencies.md)
- [最小验证结果与推导](docs/verification.md)
- [阶段零与阶段一验收报告](docs/acceptance.md)

运行阶段一：`sh scripts/run_stage1.sh`。源码在 `src/reference.py`，验证在 `verification/stage1.py`；结果、逐层缓存和模型/共享测试文件在 `results/stage1/`。固定160次明文训练损失0.67826→0.07693，梯度与溢出检查通过，定点类别与浮点5/5一致。这些不是密态训练或正式发布成果。阶段零原图结果留在 `results/phase0-reference.json`，当前统一配置已按阶段一基线更新。

构建产物位于 `build/`，`deps/` 保存本系统工具和源码；阶段一无新增依赖。正式共享发布转换、可信训练原语、范围证明、比较密钥和安全概率仍阻塞。阶段一结束，停止在参考与接口范围，不自动进入完整系统开发。

阶段二第一轮入口：`sh scripts/run_stage2.sh`。`src/mpc.py`、`src/offline.py`、`src/mpc_worker.py`实现本机两进程共享原语、可信离线预处理及精确截断；结果在 `results/stage2/summary.json`。32位215输出和小环5440输出逐位通过；13类异常明确失败。普通日志只保存公共统计，秘密测试文件留在 `build/stage2/`，消费账本位于 `state/mpc/`，禁止删除或回滚账本。配置沿用 `config/phase0.json`。

实际运行采用两方半诚实、可信离线方非串谋/不观察在线消息、正确本机连接和可信状态存储假设；进程分离不能当作跨机器认证部署。已验证共享原语，尚无完整图密态训练、安全概率或隐藏查询；第二轮实现当前环元素的缩位范围检查。阶段二第一轮结束后停止。

阶段二第二轮入口：`sh scripts/run_stage2_round2.sh`。实现全位宽布尔激活、共享批次缩位检查、真实前缀DPF比较FSS及共享小图隐藏层；结果见 [验收报告](docs/acceptance.md) 和 `results/stage2-round2/summary.json`。FSS后端是明确记录的独立实现，未复用论文优化DCF库。批次检查公开一个有效标志，不检测此前整数溢出。阶段二第二轮结束后停止。

阶段三第一轮入口：`sh scripts/run_stage3.sh`（`--smoke`只跑五节点）。真实SEAL聚合、交叉转换、精确截断和两条激活在5/16/32节点通过数值闭环；详见 [验收报告](docs/acceptance.md) 与 `results/stage3/acceptance.json`。全部解码系数已掩码，但持私钥接收者的密文视图隐私仍是安全验收阻塞。未改变模型语义或进入完整训练。

## 持续推进入口

最新验收：[持续推进报告](docs/continuation-acceptance.md)，协议与范围：[实现说明](docs/continuation.md)。运行 `sh scripts/run_continuation.sh`，沿用阶段零依赖及阶段一/三夹具。当前受限全MPC闭环已运行；真实HE算术通过但转换密文视图安全阻塞，不称完整比赛系统完成。私有材料在build，耐久消费账本在state，二者不得提交或回滚。


本轮更新（2026-10-04）：完整源码基线与新私有 BFV 解密转换见 [验收报告](docs/security-round-acceptance.md)。旧发送求值密文路径仍是明确安全阻塞；新增路径保持模型数值规则并增加交互，半诚实、可信非串谋离线方假设不变。当时训练目标概率≥1/4限制未取消；此后范围归约秘密对数及本轮训练f14路径已接入，当前条件和限制以代表性验收报告为准。

真实 Cora 实验入口：`sh scripts/run_real_data.sh`（默认96轮共享训练；下载原始锁定数据，重新生成所有私有材料）。任务、数据许可缺口、诱导子图语义及范围保障见 [真实数据说明](docs/real-data.md)。
