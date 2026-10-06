# 磁盘预算与会话保留政策（2026-10-05）

本轮只检查磁盘、增加保护和解释已有结果；没有重跑160轮共享训练、扩大节点数、压缩或修复VHD。实际清单见 [storage-inventory.json](storage-inventory.json)，逐文件历史预览留在 `results/storage/historical-preview.json`。这些清单是观测记录，执行清理必须重新预览并核验。

## 分配块实测

清单按Linux实际分配块计数，每个目录树内的硬链接只计一次。盘点主工程约131.07 GiB，14个隔离复跑目录合计约57.72 GiB；VHD文件逻辑长度和宿主可用量另列，不能把两者相加当成物理用量。

| 类别 | 主工程 | 主工程及复跑合计 |
|---|---:|---:|
| 一次性预处理（含环材料） | 97.88 GiB | 120.37 GiB |
| 一次性在线输入 | 0.293 GiB | 0.361 GiB |
| 求值工作文件（含multiply/extract密文轨迹） | 20.38 GiB | 44.74 GiB |
| 持久HE参数／密钥／图密文 | 4.54 GiB | 8.77 GiB |
| 检查点／模型／既有参考轨迹 | 0.059 GiB | 0.069 GiB |
| 消费账本及状态库 | 6.568 GiB | 7.574 GiB |
| 编译产物 | 0.009 GiB | 0.102 GiB |
| 依赖与归档 | 0.384 GiB | 5.617 GiB |

编译产物中内容SHA256相同的额外副本约64.46 MiB，逐文件清单在公共盘点JSON；依赖安装树／归档另计，未把它们全部宣称为已证明可删的重复构建。历史预览逐文件标明状态及保守可回收块数，未知状态的大小不视为可删除预算。必要检查点、账本和持久HE资产保留，历史大范围清理本轮未执行。

## 两层容量

只读Windows HKCU Lxss登记显示发行版GNN-Project使用 `E:\WSL\GNN-Project\ext4.vhdx`；WSL_DISTRO_NAME、宿主挂载和文件实际存在也已核验。Ubuntu在C盘的另一VHD不属于当前工程。起始当前VHD逻辑长度约197.67 GiB，内部可用约764.12 GiB，E盘可用约34.00 GiB。最终观测值以清单为准。`statvfs().f_bavail`反映可用块；Linux内部空闲不能替代宿主余量。

唯一运行政策为 `config/storage.json`：内部保留2 GiB，宿主保留8 GiB，每0.5秒检查。配置绑定发行版、VHD路径和宿主挂载；目录移动或发行版更换后须重新核验并更新该公共配置。映射缺失、发行版不符、挂载不符、文件不可读或余量读取失败时返回HOST_SPACE_UNKNOWN，并在产生新材料前拒绝。当前实现针对已核验的WSL环境；其他环境需补充经验证的宿主探针，不能通过虚构余量绕过。

离线预算只用公共运算计划与材料数量：两方JSON材料、FSS、环多项式预处理和工作区、每层每行乘法／提取／打包密文轨迹、输入输出及账本增长预留，并乘2安全因子。当前64节点HE/FSS请求预算4,359,636,672字节（约4.06 GiB），另加上述保留区。它是保守预算，不是实际成本，也不是文件系统配额。其他活跃／就绪会话的预算一起计入，串行化准入；执行期间仍保守保留自身完整预算，可能较早停止。

`src.offline.generate`在创建材料标识和原生材料前准入，随机生成和分块序列化期间检查；`src.runtime.launch`在启动双方前和运行中检查；`src.he.native`在长原生调用期间检查。官方应用准备、发布、资产准备、请求也先检查。主训练调度遇到拒绝／停止时原子保存停止报告及最后成功检查点。SIGTERM和Ctrl-C走停止逻辑；SIGKILL、断电留下的generating/running记录保持不可恢复、不可清理，等待独立离线核对。

在线停止先终止整个进程组，包括原生孙进程；不把半写输出当成成功检查点。中央终止标记先持久化，再在双方消费账本记录作废。持久库不可回滚。突发外部写入仍可能超过采样速度或耗尽文件系统，这不是操作系统级硬配额；保留区用于在余量触发后完成终止与持久记录。

## 状态与清理

2026-10-06修订：新会话状态为 `generating → ready → preparing → running → completed/aborted → cleaned`，停止及通知待确认时为 `stopping`。同一会话只准生成和执行一次。`ready`是尚未执行，不能清理；generating/preparing/running/stopping、无记录及无法解释的状态均拒绝清理。材料锁加准备/交付工作流锁保护完整操作，单方监督持锁至后代及通知停止。completed/aborted也必须有新事件日志中持久停止证明；旧记录不会仅凭状态名称自动补证。中央库 `state/storage/sessions.sqlite`及追加事件表、会话锁与 `state/mpc/S*-ledger.sqlite`永久保留，不VACUUM、不重置、不删除侧文件。

清理预览列出具体相对文件、逻辑大小、分配块、设备／inode／mtime／链接数，附完整预览摘要。应用发布／交付结束前仍保持running，不能在导出份额过程中清理。应用时重新核验状态、锁和每个文件属性；清单变化即拒绝。先提交cleaned状态及原始completed/aborted终止状态和清单，再删文件，删除中断后可重新预览剩余文件。复制旧材料到新位置仍被批次终止标记或消费账本拒绝。账本保留(batch, kind, index/span)，`material-identifiers.json`保留批次、材料数量、环材料ID和掩码ID；没有恢复或重新发放旧材料的入口。

删除范围采用明确允许列表：一次性preprocessing.json、input.json、ring-preprocessing、多项式求值工作文件、send/receive/trace与secure-products。保留所有成功output检查点、发布模型、同态持久密钥／参数／图密文、公共计划及策略、材料标识、metrics、接收端最终交付、验收报告、验证端数据与证据。不会递归删除整个会话或实验目录，也不依据文件年龄推断终止状态。

```sh
# 只预览中央库已知且终止的会话；ID来自本轮请求或训练报告
python3 -m src.retention preview --session <会话ID> --output results/storage/cleanup-preview.json
# 审阅具体清单后应用，状态与文件属性会再次核验
python3 -m src.retention apply --preview results/storage/cleanup-preview.json
# 刷新主工程和全部隔离复跑目录的只读盘点
python3 scripts/storage_inventory.py
```

大范围历史删除本轮未执行。旧会话没有新生命周期锁／记录，清单分别列出双方completed/aborted_burned证据以及未完成／未知状态；即使有终止证据，也不能由新命令直接删除。历史迁移需逐项确认会话已离线、不会恢复、检查点与材料标识留存，再建立可信终止记录；当前未实现自动推断或迁移。隔离复跑目录的账本不得并入或替换主工程账本，不能整目录删除。

新官方训练每次成功检查点与报告持久提交后自动预览／清理一次性文件；失败且已确认aborted时同样清理。新发布在模型链接和报告保存后清理。新请求在两方目标份额成功导出后清理。成功检查点目前全保留，未实施淘汰旧检查点。独立底层验证夹具默认延迟清理，便于其明确的故障注入；只能用同一终止清理命令处理，不作为生产实验入口。独立验证现已能在一次性输入删除后用保留的检查点、f12/f7模型、公开作业模板及最终交付核验，不重新生成旧输入。

删除Linux文件本轮没有压缩VHD，宿主可用空间不承诺随之回升。2026-10-06新增清理前后内部/宿主可用空间观测、成功unlink文件分配块和当时最后链接分配块统计，记录于持久事件表。`reclaimable_upper_bytes`仍仅为预览上界；删除块统计及可用空间差值也不能相互替代或当作已证明的实际回收量。重复构建文件按内容哈希列出，依赖安装树分别计量，均没有擅自删除。

异常交付不重执行密码协议，没有补齐入口；失败清理必须等相关执行器停止确认，终止通知由各角色辅助进程保存。当前角色仍共用UID，OS受限执行器及角色清理尚未部署。新验收与权限阻塞见 [lifecycle-role-acceptance.md](lifecycle-role-acceptance.md)，旧报告和历史预览保留。

## 改动验证

`python3 verification/storage_checks.py`覆盖内部不足、宿主不足、宿主未知、生成中不足、执行中不足及孙进程停止、单方故障辅助进程监督、活跃／就绪／未知状态拒绝、预览变化拒绝、密文轨迹清理、保留成功检查点、旧材料复制后拒绝。`verification/training_storage_checks.py`覆盖首轮无检查点拒绝与后续停止报告保留成功检查点；不运行训练。`verification/demo_checks.py`覆盖真实后端新请求的独立批次／环材料／掩码ID及自动清理。`verification/retained_query_checks.py`只在独立验证端复核已有模型与最终交付，不重执行后端。聚合证据见 [storage-delivery-results.json](storage-delivery-results.json)。
