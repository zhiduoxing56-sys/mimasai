# 依赖版本来源与协议调查

新增依赖均下载、解包和构建在项目内部 deps/ 与 build/，未执行系统安装。初始系统 Python=/usr/bin/python3 3.12.3、Git=/usr/bin/git 2.43.0、curl=/usr/bin/curl 8.5.0；没有 g++、CMake、Ninja 或 Make。未调用挂载盘中的可执行文件。现有操作系统运行库不属于新增安装；本地 PDF 工具也使用现有系统的部分传递运行库。

## 已获取与构建

| 依赖 | 来源与版本 | 路径与实际结果 |
| --- | --- | --- |
| Microsoft SEAL | 官方 tag v4.1.0，MIT；https://codeload.github.com/microsoft/SEAL/tar.gz/refs/tags/v4.1.0 | deps/SEAL-4.1.0；SHA256 337e847b01827adc2d3fd9ac8b79038651c425f8c723110522d33a3d169de0f9；静态库 build/seal/lib/libseal-4.1.a 构建成功 |
| GCC/G++ | Ubuntu noble 包，13.3.0-6ubuntu2~24.04.1 | deps/toolchain/usr/bin/x86_64-linux-gnu-g++-13，实测13.3.0；编译器后端、as、ld和C++库路径均项目内 |
| CMake、Make、binutils | Ubuntu，3.28.3-1build7、4.3-4.1build2、2.42-4ubuntu2.10 | deps/toolchain/usr/bin；不需要Ninja |
| 开发头文件及编译运行库 | libc6/dev 2.39-0ubuntu8，linux-libc-dev 6.8.0-31.31，GCC13开发库、GCC14运行库等 | 仅 dpkg-deb -x；各包精确版本及SHA256见dependency-lock.json |
| pypdf | PyPI 官方元数据，6.19.0，BSD-3-Clause | deps/python；wheel SHA256 7e5d6e730e7dae87d560a2cee218b852f6498c8be61966f3cd02ead971e48d14；英文文本提取成功 |
| Poppler | Ubuntu 24.02.0-1ubuntu9.9，poppler-data 0.4.12-1，GPL系列许可 | deps/toolchain；用于PDF核对，不链接进作品协议；中文映射指定本地路径后成功 |

构建命令和参数保存在 scripts/build_he.sh：Release、C++17，关闭可选 MSGSL、zlib、zstd 和 HEXL，关闭外部依赖自动下载，保持透明密文检查开启。128位检查由程序显式启用；没有 sec_level_type::none。本地编译入口 scripts/cc.sh 与 cxx.sh 指定 sysroot、include 和工具搜索路径；ar/ranlib也指定本地路径。

网络获取初始失败原因为沙箱代理127.0.0.1:12334不可达；升级联网后成功。部分apt索引版本（libc6-dev 2.39-0ubuntu8.8、linux-libc-dev 6.8.0-139.139）404，改获取镜像仍有的基础版本，没有执行apt系统更新。libopenjp2首次502，重试成功。SEAF按main查询404，官方元数据确认默认master后成功。上述失败未计为获取成功的依赖。

下载包在 deps/downloads，哈希和版本在 config/dependencies.lock.json。`python3 scripts/unpack_deps.py` 只核对并从已有包恢复本地依赖；不会联网或安装系统包。重取Ubuntu包用 `apt-get download 包名=锁定版本`，在deps/downloads执行。镜像将来若移除版本，须报告获取失败，不静默更新。PDF中文提取编译脚本源码为 scripts/pdf_text.cpp，构造GlobalParams时显式指定deps/toolchain/usr/share/poppler；初始工具默认系统路径失败的日志保留，不依赖乱码文本下结论。

## 训练协议来源及复用结论

比赛参考文献5对应 [SecGNN原论文](https://arxiv.org/html/2202.07835)，作者仓库为 [songleiW/SecGNN](https://github.com/songleiW/SecGNN)。固定提交8338ea45bea5ea073105977ea1e495e2351c4a35，已下载三个小文件并核对Git blob与tree一致；证据在results/secgnn-source-audit.json。IV-B假设三方半诚实、不串谋；V-D1 Subroutine2使用随机旋转、成对PRF及三方零和相关量实现秘密数组访问。VII-A指定64位环、15位定点精度。作者仓库API license=null，递归tree未发现许可证，不推定可直接复制复用。

作者mpcUtil.cpp在一个进程同时访问两份额；行7附近固定key12/key13/key23；乘法行72至122的三元组pop_back被注释且逐份额普通除以t；数组访问行302起调用rand/srand。这些是源码事实，说明不能将其运行视为分布式安全实现。没有替作者补安全结果或构建完整数据集训练。

| 算子 | 原始位置和机制 | 适用条件及当前缺口 |
| --- | --- | --- |
| 秘密索引 | SecGNN V-D1 Subroutine2；原文引用Blanton、Kang、Yuan ACNS2020及Araki等CCS2016 | 索引有效、三方视图分离、PRF密码安全、计数唯一；可信分布式代码未核实可直接使用 |
| 乘法 | Beaver离线三元组及ASS.Mul | 三元组新鲜、共享环一致；不得复用、经销商不得与计算方串谋 |
| 除法 | SecGNN V-B式11，比赛4.6，Newton倒数迭代 | x>0、初始0<x*y0<2、固定点不过流；初值域和迭代误差需建立 |
| 平方根倒数 | SecGNN V-D2式15 | x>0、适宜初值和收敛界；零度先正确加自环；源码普通sqrt不是安全协议 |
| 指数 | SecGNN V-E2式16，比赛4.9，重复平方近似 | 底数和输入范围受限，截断误差会积累；最大值减法只给上界0而非下界 |
| 对数 | SecGNN V-F式17，比赛4.7 | x>0，概率下界、初值和迭代域需校验 |
| 比较 | SecGNN V-E1安全MSB；HyGNN IV-C式1及DCF | 定点有符号环语义、位宽范围；HyGNN字面算法失败，DCF密钥未实现 |
| 截断 | SecGNN指向SecureML；HyGNN指向SEAF | 不能用普通份额除法；下面两来源保证不同，尚未选作品协议 |
| 最终概率 | 比赛3.2.2；HyGNN V-B Step7引用SEAF | 查到作者库调用Softmax，但尚未核实目标32/7参数和完整函数，未计实现 |

[SecureML原文](https://eprint.iacr.org/2017/396.pdf) 第4.1节定理1给出带范围限制的概率截断：l>lx+1、lD≤lx，在给定值域以至少1−2^(lx+1−l)概率只产生至多1个低位误差。不能把它说成对任意输入精确截断；多次调用需累计失败概率。负数规则也不能自动等同本轮reference的floor舍入。

[SEAF原论文](https://www.usenix.org/system/files/usenixsecurity25-guo-hao-seaf.pdf) 第2节区分精确截断、允许1位误差截断、截断降环与符号扩展，依赖SirNN/Cheetah原语；适用调用要指定公开MSB条件和输出环。作者 [SEAF仓库](https://github.com/geralt-tian/SEAF) 固定提交dc264a421ea094984d2f4ad1b344f3a00062dfbe，MIT许可证已保存。下载的SCI/src/BuildingBlocks/truncation.cpp使用比较、环回绕和B2A，包含参数约束，未构建其OT后端。

SCI/tests/activation/bolt_softmax.cpp的安全路径调用fpmath->softmax_fix，明文std::exp位于参考核对函数；不把后者当密态运算。测试默认37位环、12位小数，且另有IRON Softmax测试，不能未经适配声称与HyGNN的32/7一致。最终概率协议仍需要指定具体安全函数、归一化误差、溢出和许可证继承。

## 同态提取打包来源

HyGNN III-C定义ExtractConst与LWEstoRLWE接口、IV-B调用它们，但未给出实现或键明细。其引用25的作者 [ArcEDB](https://github.com/zhouzhangwalker/ArcEDB) 固定提交e25a32dfb4a1585a95993f4b7ccd9c8f6afae4bc；MIT许可证及packlwes.cpp/repack.cpp已获取。packlwes.cpp包含Galois键生成、系数模数N逆元和trace；repack.cpp含TFHE到CKKS路径，二者不能混用。本轮SEAL实验独立实现直接提取与简单trace打包，原库未构建、未声称已复用其批量方案。评估键、噪声和输出细节见verification.md。

## 阶段一依赖

仅使用已有 /usr/bin/python3 3.12.3 标准库（math/json/decimal/hashlib/secrets），没有新增安装；Decimal概率对照精度80位。沿用项目内SEAL4.1.0二进制运行统一小图密码回归，未重配安全参数。

## 阶段二精确截断与共享乘法依据

本轮新增实现仍只依赖已有 `/usr/bin/python3` 3.12.3标准库（socket、sqlite3、struct、secrets等），没有安装ABY、MP-SPDZ或OT依赖。运行IPC需要环境允许AF_UNIX socket；沙箱中继承socket的构造曾被EPERM拒绝，获准在沙箱外执行本机验证。这个运行权限不构成跨机器部署授权。

- [ABY原论文，NDSS2015](https://www.ndss-symposium.org/wp-content/uploads/2017/09/08_2_1.pdf)：III-A2（PDF第5页）给出Z/(2^l)三元组乘法；III-B2（第6页）给出布尔AND三元组；IV-D（第7页）明确可用布尔加法电路转换算术共享，ABY实际优化路径使用Yao，不能说本项目复制该后端。原文公共项给P1，本实现给S0，均为只分配给一方的角色选择。
- [MP-SPDZ官方README](https://github.com/data61/MP-SPDZ/blob/d39bd91c08801cb195012d6df5267eac3a9c5ef1/README.md#mixed-circuits)：Mixed circuits / Classic daBits / Local share conversion明确支持模2^k域、本地份额位分解及秘密加法，并要求加法共享无MAC。它提供方法依据，不是本轮实际依赖或已跑通其截断函数。
- [Rotaru–Wood原论文，2019/207](https://eprint.iacr.org/2019/207.pdf)：§1.1 PDF第3–4页阐述双域随机位及掩码输出转换；§3第10页说明环适用性；§4.1讨论可信性之外的主动一致性生成。本轮可信离线方直接生成相同位的两种份额，B2A只打开b XOR r，用公开位在r与1−r之间选择；未实现论文的主动生成/认证协议。适用任意n位环，本轮32/7，舍入通过符号移位电路固定为floor，无符号/低位公开。

ABY作者仓库已核实默认分支public，固定提交88fed3ef6789580cac342201e135a358a083ca36；该提交根LICENSE为LGPLv3，已下载，未复制其源代码。MP-SPDZ固定提交d39bd91c08801cb195012d6df5267eac3a9c5ef1；License.txt包含主体BSD3-Clause及第三方条款，GitHub自动标签为NOASSERTION，不能把全部组件简化为同一许可证。本轮仅引用文档方法，未构建或复制其源码。两篇论文保留各自版权说明，下载不等同源码授权。

获取记录与SHA256在 results/stage2/sources.json，离线PDF/许可证/README在deps/downloads，提取文本在results/stage2。作者ABY链接返回HTTP200 HTML而非PDF，已保留失败响应并从NDSS官方PDF成功取得；对旧master提交查询HTTP422后核实了public分支。未把HTML响应当论文获取成功。

## 阶段二第二轮来源与获取

未安装新依赖；运行使用系统Python3.12.3标准库，随机量使用secrets，SHAKE使用hashlib。实际获取文件、URL、字节数和SHA256见 results/stage2-round2/sources.json；环境核查见 dependency-audit.json。

实际DPF算法依据：[BGI Function Secret Sharing: Improvements and Extensions](https://eprint.iacr.org/2018/707)，§3.2.2/定理3.3（PDF第9页）、图1（第10页）。本项目独立实现该算法及固定数量前缀组合比较，不复制第三方源码。SHAKE选择参考 [Python官方hashlib文档](https://docs.python.org/3.12/library/hashlib.html#shake-variable-length-digests)，它是实现选择，不声称由原论文指定或经审计。

调查了 [myl7/fss](https://github.com/myl7/fss) 固定提交5771a864e4970d8645ddd2203523afc5091b8205，Apache-2.0；DPF/DCF头与许可证已保存。其DCF支持严格无符号kLt/kGt，调用方提供种子，使用AES/MMO及CUDA相关头。当前没有nvcc/CUDA头，因此未构建或链接，不宣称其官方内核已验证。

另调查 [xingpz2008/dealerless-FSS_public](https://github.com/xingpz2008/dealerless-FSS_public) 提交e8fefb537253ee5b0317ea484c934656f09a66f5，Apache-2.0；保存DCF源码和许可证。该作者路径需要EzPC FSS/SCI、cryptoTools、通信与OT等依赖；GroupElement为模2^Bout群，调用secure_prng，端点及整个调用栈未本地验证，不直接复用。优化DCF依据 [Boyle等2021论文](https://eprint.iacr.org/2020/1392)，本轮不声称落实其优化内核或分布式密钥生成。

## 阶段三第一轮构建及协议来源

新增源码src/he_bridge.cpp，脚本sh scripts/build_stage3.sh复用项目内GCC13.3与静态SEAL4.1.0，不安装依赖、不调用挂载盘工具、不重建另一套SEAL参数。二进制build/he_bridge；Python桥src/he.py只用已有标准库。在线生成随机系数使用系统secrets，密钥及加密随机量使用SEAL默认密码随机工厂；未设置固定种子。所有新增源、下载论文及许可证摘要见results/stage3/sources.json。

提取/trace按阶段零已有独立实现及ArcEDB固定提交参考继续扩展，未链接ArcEDB代码。交叉持钥/转换依据HyGNN V-B Setup与Step2（PDF第7–8页），本轮扩充为完整多项式系数掩码。老师论文局部描述不提供普通SEAL求值密文的完整视图净化实现，记录为缺少协议细节。

补充原始来源：[Hwang、Min、Song，Ciphertext-Simulatable HE from BFV with Randomized Evaluation，2025/203](https://eprint.iacr.org/2025/203)，原文§1.1/§1.2说明HE的IND-CPA不足以推出2PC中求值方输入隐私；给出需要逐步随机化的构造。论文CC BY，仅下载和分析，未复制实现或宣称已完成适配。PDF与提取文本已保存。不能依据本次噪声余量选择“安全”噪声淹没幅度：还需公开最坏误差界、统计安全参数、余量及SEAL模链适配。

GitHub网页工具首次获取SEAL/ArcEDB指定页面返回cache miss，采用已有固定版本本地源码依据；ePrint主页面查询与原PDF下载成功。下载曾被沙箱代理拒绝，经批准联网后成功，未把失败获取计为成功。

## 持续推进更新（2026-10-04）

本轮无新增安装，仅Python3.12标准库和既有SEAL4.1.0。本轮补取SEAF固定提交的fp-math.cpp、fixed-point.cpp及作者Chapter5原文，只作依据未链接第三方内核；函数调用、位宽、常量、MIT许可与PDF403失败结果见continuation.md和results/continuation/acceptance.json sources。

本轮将唯一依赖锁移到版本管理config/dependencies.lock.json。runtime离线恢复只校验并解包锁内44份deb/SEAL归档，缺少任一必需包会列名报错。可选论文、作者代码与PDF/Python分析依赖不属于最小运行恢复；未声称所有系统依赖可离线从源码重建。
