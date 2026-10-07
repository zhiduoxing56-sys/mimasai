# 自有源码审阅入口与发现

2026-10-07当前状态以[本机部署验收](local-page-acceptance.md)和[机器记录](local-deployment-progress.json)为准：冻结部署`1c8f376`的六个真实身份128项检查通过，现有发布资产与账本迁移保留inode。以下较早段落的“同Unix用户”“未交付页面”属于当时状态；当前页面空闲视图已实际截图，但首次真实查询失败，成功交付仍未完成。本轮不重训、不扩大图、不改变数值语义。

新增审阅入口：

|主题|源码入口|证据/验证|
|---|---|---|
|固定角色执行器及真实UID授权|src/role_broker.py、deployment.py、isolated_actor.py|results/local-page/real-uid-permissions.json（128项实测）|
|角色账本与管理员迁移|src/role_state.py、scripts/install_local_roles.py|results/local-page/migration-evidence.json（同inode/迁移时SHA-256）|
|协调器生命周期与页面允许列表|src/demo_coordinator.py、demo_page.py、public_projection.py、ui/|verification/local_page_checks.py（既有7项短测试）；真实成功查询仍待验收|
|失败尝试持久记录、禁止自动重跑|scripts/local_deployment.py|verification/deployment_diagnostics_checks.py（新增5项短测试）|
|只读单会话管理员诊断|scripts/diagnose_local_query.py|只读状态/阶段/错误码/空间及准备文件元数据；不读取账本/份额|
|实际浏览器及公开证据包装|scripts/capture_local_page.ps1、build_page_evidence.py|results/local-page/connected-ready.png（实际空闲页，非成功预测）|

`python3 scripts/build_page_evidence.py`另外生成`review/local-page-evidence.tar.gz`，只选择明确列出的公开JSON和截图，不扫描角色私有目录或浏览器配置目录。`results/page/access-link.json`、`browser-session.json`中的访问能力/cookie不纳入两个包。源码包清单记录当前源码提交；实际运行证据另行绑定冻结提交，不能把未部署修复称为运行结果。

|主题|准确源码入口|验证入口|
|---|---|---|
|真实同态聚合与旧转换|src/he.py:aggregate；src/he_bridge.cpp 的 eval、extract/pack、decrypt|verification/stage3.py、two_layer_he.py（旧转换仅诊断）|
|新私有输入解密|src/he_secure.py:secure_convert、round_phase、add_bits；he_bridge.cpp 的 ring_preprocess/ring_evaluate/export_ring_inputs|verification/bfv_round.py、he_private_decryption.py|
|持久消费/通信/精确截断|src/mpc.py:Materials、Channel、Engine；src/offline.py；src/mpc_worker.py|verification/stage2.py|
|缩位范围与激活|src/mpc.py 的 range/relu；src/fss.py；src/mpc_worker.py 分派|verification/stage2_round2.py、paper_activation.py|
|秘密索引|src/operators.py:gather、indexed_aggregate|verification/operators.py、training.py --indexed|
|共享训练|src/operators.py:train_step、bounded_matrix、cross_entropy、convergence_step|verification/training.py、loss_domain.py|
|持续共享发布|src/model.py:publish、load、binding|verification/publication.py|
|秘密概率|src/operators.py:probability、divide_unsigned、maximum|verification/operators.py|

执行 `python3 scripts/build_review.py` 输出 review/privacy-gnn-source-review.tar.gz 与 SHA-256 文件清单，严格只选 Git 跟踪自有源码、公共配置、合成验证夹具、脚本及说明。拒绝符号链接与未知扩展。不包含第三方论文/作者实现、密钥、份额、预处理、多项式工作文件、掩码、账本、结果载荷或构建产物。源码中测试恢复函数属于独立验证端，审阅包包含它以供检查，不表示服务器可调用。

本轮审阅发现与修复：

* 早期源码未完整跟踪，已补齐完整基线；依赖锁原在 ignored results 中，移到 config 唯一锁文件；旧 provenance 脚本会覆盖锁，改为只写观测 inventory。
* 旧 HE 路径把求值密文发送给交叉私钥持有者，完整误差视图缺乏保护；旧路径保留明确标记，新增不发送求值密文的私有解密。转换类型现在必须显式指定，禁止默认静默回退旧路径。
* 新大环预处理增加全局随机 material_id 的持久唯一预留，跨批次重贴标签也拒绝；全部在连接前预留，失败后不能回收未使用部分。主动攻击者篡改 ID、回滚数据库、复制主机不在半诚实保证内。
* 服务器只由 settings() 读公共配置；参考 config() 及明文夹具在验证端。worker 的审计 hook 拒绝读取 results/verification fixtures/另一方私有目录；实际轨迹验证只读取自身文件。该 hook 不是 OS 隔离或恶意代码防护。
* 新服务器原生路径 export_ring_inputs/ring_evaluate 不调用 Decryptor，private_decryption 在进入旧 decrypt 分支前返回。公开通信仅掩码打开值及结构，独立验证端才运行 official decode/noise oracle 和恢复输出。原生程序包含测试 oracle 命令，不代表在线服务器使用它。
* 正式共享模型 ID 是独立随机值，公开绑定只有结构/数值/顺序/版本。HE 参数/公钥摘要是公开材料摘要。own he.json 的 peer.sk 完整性摘要属于仅本地私有文件，不发送或记录到普通消息；不把该摘要当成认证或秘密内容无泄露的公共标识。参考模型权重摘要保留验证端范围。

审阅未发现新增在线恢复或明文代算。服务器 Python 与原生子进程共用一个角色目录；本机同一 Unix 用户可绕过该约束，部署认证与用户隔离仍待实现。协议采用可信设置且离线方不观察在线消息，不能宣称主动安全。

本轮新增审阅入口：verification/trained_he_chain.py与scripts/run_trained_he.sh展示真实训练份额→发布→在线本地load的完整证据；src/mpc_worker.py的matmul/model_layer与shared_aggregate、src/mpc.py的资源规划；src/operators.py:negative_log、cross_entropy(loss_mode)、src/numerical.py:negative_log_reference、verification/extended_log.py。测试调度launch在超时后终止所有子进程，永久保留预留账本。每操作/子项RSS记录是进程至该时点累计highwater，不能称为该算子独立峰值。

扩展对数旧失败初始化真实训练入口：verification/extended_failed_training.py；只从合成初始化构造训练输入，使用真实两进程共享协议，独立验证端恢复完整状态进行对照，不参与主链路模型替换。

真实数据轮新增：`src/data.py:cora` 仅为拥有者导入；在线 worker 审计拒绝 data 与下载档案目录。`src/operators.py:check_dot_range` 在执行点积前验证秘密行L1界；`verification/range_budget.py` 覆盖安全接受、越界拒绝、持久重放及连续消费区间。`verification/real_data.py` 每轮把同角色上一检查点的权重份额送入新会话，验证恢复不作为模型输入。`verification/real_chain.py` 的 owner_bundle 直接编码本 Cora 传播矩阵，不调用合成 `fixture(16)`；`verification/trained_he_chain.py:run` 复用统一推理流程。模型文件只同角色复制。`scripts/run_real_data.sh` 是统一入口。数据、训练完整状态和原始档案仍不进审阅包。

新增布局审阅：src/model.py 的 additive-model-v2绑定 feature_order/class_order；mpc_worker 首层核对公开特征顺序，he.aggregate 核对输出列。旧v1历史文件不会作为新模型加载。src/sparse_reference.py及cora_full_reference.py只有拥有者/验证端入口，worker不会导入；full_domain_audit.py的定位数据只在ignored验证结果。HE_PUBLIC_DOT_BOUND_UNSAFE是合法归一化P输入假设下的公开整数预算，并非加密P范围证明。

无人值守轮：src/application.py提供拥有者/可信离线/本机调度命令；src/runtime.py抽取原有launch，不新增通信协议。src/query.py验证本机授权策略及最终选择，mpc_worker的delivery只落盘最后一项，src/receiver.py只允许读取目标份额交付目录。verification/application.py负责完整模型/相位/状态恢复对照，与接收者隔离。src/operators.py:average_signed为任意正样本数精确向下平均，train_step后向输入改用在线验证的backprop_state界；verification/average.py覆盖MIN、小环穷举和三样本真实训练。所有原材料、历史账本及已有角色私有文件保持原位，不纳入审阅包。

协调器视图修复：初版src.application曾在循环中解析两方检查点/目标结果，虽未调用恢复，其完整视图仍不符合最小角色原则。现在src/role_io.py在分别受审计的独立角色进程里准备发布输入和查询输入、导出自身最终目标份额；协调器仅收取公共状态，不解析这些秘密文件。模型资产同角色硬链接无需读参数。旧临时5轮实验保留为正确性诊断，新版本再用新材料验收。物理UID权限仍非隔离证明。

范围政策衔接：src/ranges.py唯一从operand_bounds_real导出整数半开区间与包围位宽；Engine/CostCounter共同调用已有秘密有符号比较实现非二次幂验证。训练传播以真实radius计算L1限额，HE也用同一radius证明并在线检查输入，不仅按包围幂计算。score32的稳定概率先验证差分不越环，近似核未改变。公开数值配置绑定握手。V验证同时检查原检查点→刷新f12→秘密floor5并刷新f7三者完整值一致，正式协调器仍不解析参数。

本轮补充：src/query.py同时核对变换/聚合尺度和概率升尺度，verification/application.py实际注入目标、接收者、模型、尺度、词列、HE参数、耗尽及环掩码打开后断连。scripts/summarize_application.py只读公开验收报告，按线上操作划分成本并单独记录握手，HE/BFV嵌套组件不重复计费。verification/application_metrics.py是独立验证端：高精度概率字符串必须Decimal比较，保留旧派生报告并重算分类指标；不生成在线答案，不改变协议输出。原科学计数法按字符串排序曾误报分类不一致，已保留错误证据与回归样例。

## 磁盘保护与交付轮审阅入口（2026-10-05）

* `src/storage.py`／`config/storage.json`：核验发行版、VHD宿主挂载与真实可用块；预算包含两方JSON、环工作区、每行原生密文轨迹和持久记录。宿主未知显式拒绝；会话持久状态、并发准入、SIGTERM处理、永久作废标记不依赖可删除材料。
* `src/offline.py`／`src/mpc.py:private_write`：材料生成前准入、生成与有界分块序列化中检查。保留材料ID，无完整材料大小的第二个JSON字符串。Materials同时核验中央终止标记和原角色消费账本；不改消费、截断或算术语义。
* `src/runtime.py`／`src/he.py:native`：执行前与运行中检查；终止整个进程组及原生孙进程，非零退出不能作为成功；单方故障辅助进程也持续持锁监督。应用发布／结果导出结束前保持running，禁止清理；训练停止报告原子保留成功检查点。
* `src/retention.py`：只接受已知completed/aborted/cleaned，持锁预览、摘要和文件属性重验，先持久记录终止／清理状态再删除明确一次性允许列表。保留全部输出、模型、密钥、公共配置、ID、metrics与账本；不按年龄清理、不清理未知旧会话、不恢复旧材料、不做VHD维护。
* `scripts/storage_inventory.py`：独立读取分配块、链接与公共状态，主工程／14复跑目录分开记量，重复编译文件做内容哈希。历史逐文件清单不执行删除，公共文档仅保存摘要和位置。
* `scripts/demo.py`／`src/application.py`／`src/role_io.py`：只复用现有发布模型；新请求使用新批次和真实后端，独立角色进程处理各自份额，独立接收端恢复目标最终概率。目录fsync新增精确导出目录许可，不授予其他结果文件读取；局部异常仅记录类型、errno、源码位置，不把秘密值写入错误日志。
* `verification/storage_checks.py`、`training_storage_checks.py`、`demo_checks.py`、`retained_query_checks.py`：仅覆盖本轮空间、状态、清理、检查点和新请求边界；故障worker是合成生命周期夹具，不是替代线上后端。原application验证器兼容清理后的公开模板和中央重用拒绝，独立恢复模型与最终查询核验仍在verification侧。
* `verification/feature_control.py`：固定已有数据／种子／划分／训练验证选择规则的词特征浮点对照；标签无关结果复用已有记录。`verification/numeric_attribution.py`：既有检查点单步消融和既有权重拒绝边界审计；数值协议未修改。`scripts/report_storage_delivery.py`仅汇总公开分类／成本证据。

发现并纠正：原生multiply/extract/packed密文trace需要单独计入预算与一次性清理；应用只在backend退出后就声明completed会允许清理与导出竞态，因此延迟到两方交付／模型持久链接后终止。历史没有生命周期锁的目录不能自动迁移或删除。全部新源码、公共配置与聚合报告纳入更新审阅包，秘密运行目录和账本不纳入；已有半诚实、可信非串谋离线方和可信持久存储假设保持不变。同Unix用户的Python路径审计不等于OS隔离，未交付页面。
