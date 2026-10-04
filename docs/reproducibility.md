# 可重现源码基线

完整自有基线提交 `e59e2015ce85359479d103a307aaed09602f9634` 将早期未跟踪源码、脚本、公共配置及合成夹具全部纳入 Git。后续提交在此基线继续；原始材料没有修改。单一计算配置仍为 config/phase0.json，合成明文只在 verification/fixtures，依赖唯一锁文件 config/dependencies.lock.json。

入口：`python3 scripts/replay_clean.py`。从 HEAD 建立新的 detached worktree，检查没有 deps/build/state，按 SHA-256 只复制公开锁定的44个运行时归档，重新解包编译工具、从 SEAL 4.1.0 源码构建库和桥，运行 stage1、三轮共享训练、真实训练份额发布/推理、旧 HE 正确性诊断及新私有解密两层分数。密钥、模型随机标识、会话和全部预处理均重新生成。新目录账本保留，不复制历史密钥、份额或账本。

运行基础：Linux amd64、系统 /usr/bin/python3（已测3.12.3）、Git、dpkg-deb 以及基础 Linux 动态加载器/libc。编译器/CMake/make 采用项目内部锁定工具路径。当前44个必要归档齐全；这证明运行时源码最小复跑，不证明宿主操作系统或全部研究资料都能离线重建。锁文件还记载早期分析附件，最小复跑不要求它们。`record_provenance.py` 只写 results 中的观测清单，不自动覆盖锁定版本。

results/reproducibility/clean-replay.json 记录实际提交、目录、会话和用时；失败日志不包含私有载荷。state/deps/build/results/参考资料/review 均排除 Git。state 中已有及本轮账本永久保留，不能通过删除或重置重跑同一材料。
