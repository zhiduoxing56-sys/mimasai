# 本机真实数据训练与授权查询

完整入口（恢复已有锁定依赖并构建）：

```sh
sh scripts/run_application.sh --nodes 64 --steps 96 --validate --faults
```

该命令创建随机实验目录、真实Cora数据准备、160轮浮点/定点对照、指定轮数两进程共享训练、持续共享发布、HE资产准备、五次新请求及独立结果接收。前两次都是同模型HE/FSS请求，然后执行同模型共享/FSS、HE/布尔、共享/布尔。`--validate`独立启动拥有者验证端，恢复检查完整状态及同模型四路径；它不是查询者权限。`--faults`增加真实拒绝与消费测试。默认节点数和训练轮数来自唯一config/phase0.json；命令行节点数是公开实验规模选择，数值规则不另建配置。

运行依赖使用既有44份锁定归档，缺少归档时按名称报错。数据只下载官方固定SHA256的Cora，不下载GCN框架或训练模型。许可仍缺原归档明示再分发授权，数据不纳入Git/审阅包。预处理、划分、诱导图语义与原全图差异见real-data.md；正式入口不依赖固定五节点夹具。

## 独立命令

下列ID均来自上一命令JSON，不是秘密内容摘要。

```sh
# 拥有者：数据校验、图准备、同角色输入份额
python3 -m src.application prepare --nodes 64 --download --target 35
# 输出 experiment_id，后续用 <实验ID> 替换

# 可选独立参考；train自己包含参考，不必两次执行
python3 -m src.application reference --experiment <实验ID>
# 拥有者/独立验证端调度真实服务器；检查点逐轮持久保存
python3 -m src.application train --experiment <实验ID> --steps 96
# 中断后从成功检查点继续，用全新批次；旧失败材料不恢复
python3 -m src.application train --experiment <实验ID> --steps 96 --resume

# 各方原权重份额持续发布；秘密f12→f7，范围检查和刷新
python3 -m src.application publish --experiment <实验ID>
# 拥有者生成交叉密钥/图密文等持续资产；在线只装自身授权材料
python3 -m src.application provision --experiment <实验ID>

# 同一已发布模型可重复请求；每次此命令生成新的请求ID
python3 -m src.application request --experiment <实验ID> --route he --activation fss --target 35
# 离线可信方；不读取在线输入或消息
python3 -m src.application offline --experiment <实验ID> --request <请求ID>
# 两台独立服务器及本机调度器，只交付目标最终结果份额
python3 -m src.application execute --experiment <实验ID> --request <请求ID>
# 独立接收端：仅读取execute输出的receiver_directory中两个文件
python3 -m src.receiver <receiver_directory>
```

`train --checkpoint-report <真实共享训练报告>`可接入已有真实检查点，必须状态为SHARED_TRAINING_PASS且编号顺序、规模匹配；它不接收浮点模型或参考初始化替代品。该选项用于本轮持续运行训练接入应用，无参数恢复再共享。测试验证与正式发布源码分离：src.application.publish不恢复权重，verification/application.py才可为对照恢复。

## 权限、消息与交付

本轮目标节点编号公开，模型结构/类名和版本公开。全图秘密传播后选择授权目标；不声称隐藏目标。拥有者控制每方query-policy.json中的model/allowed_targets/receiver_id，服务器在连接前检查请求，握手绑定公开交付计划；最终deliver只能接在同形状秘密probability之后。模型、类/词顺序、环、尺度绑定一致。权限为本机受控文件，不是密码认证或操作系统隔离。

所有中间值仅留在线进程内。delivery模式的服务器output只包含最后一个目标概率份额向量；不会写全图概率、隐藏层或模型参数给接收者。查询者目录只接收授权最终结果的两个份额文件，接收端审计禁止读取build/state/其他results。模型权重文件仅在服务器目录持续使用；完整状态恢复由单独verification进程进行，其输出不进入接收者目录。

每次请求单独生成Boolean/arith/daBit/FSS、R_Q三元组和掩码种子；离线准备先于在线input.json。请求开始与离线开始标志持久记录，服务端连接前预留整批，全局材料标识继续防跨批次重贴标签。失败不交付结果，原材料不能重试；创建新请求获取新材料。模型、公钥/交叉私钥和原始图密文可持续复用，不复用求值工作目录或请求随机量。程序没有legacy自动回退。

无网页：当前仍同一Unix用户和应用层审计，未完成操作系统角色权限隔离；保留CLI，避免页面获得拥有者或验证端权限。CLI每次实际调用后端计算并由独立接收端恢复，不播放预先结果。

## 数值容量与平均

32位/f12保持不变。后向dH在乘法结束后秘密检查backprop_state=1；掩码后的dZ0同界；PᵀdZ0和XᵀdT0使用此界并秘密检查操作数。对应Xᵀ行L1限额为524287，不再使用前向state16导致的32767限制。守卫条件是协议前置条件：不满足就拒绝，不能把小图观测当通用证明。矩阵计算仍完整点积一次截断。

训练掩码可包含任意正整数个样本。二次幂计数沿用原精确移位；其他计数使用32位秘密符号、绝对值的无符号解释、秘密条件加count−1、恢复除法及秘密恢复符号，实现floor(signed(x)/count)。MIN的无符号绝对值2^31合法；分子≤2^31+count−1<2^32，计数公开正且<2^31。符号和余数不打开。损失累加先要求公开保守界count×(f×round(2^f ln2)+2^f)<2^31，随后一次精确平均；参考使用相同floor。梯度仍近似标准p−y，不是近似概率或损失的精确导数。

## 结果与成本

每次运行results/application/<实验ID>/manifest.json记录数据和版本、实际检查点与发布成本；training/reference.json记录参考曲线、实际成功轮次和逐轮成本；request-<请求ID>.json记录材料数、阶段线上字节、轮数、时间、累计RSS；receiver/<请求ID>/result.json只含授权概率。验证生成acceptance.json，pipeline.json记录全流程。消费账本在state/mpc长期保留，私有文件不提交。

线上量只计两方向socket实际发送含头，轮数为配对交换；离线生成、构建、文件分发和接收者文件大小另记。每层/概率组件是父项分解，不重复加总；RSS是每进程累计highwater。新路线不等同原论文低交互转换，legacy_ciphertext继续安全阻塞。半诚实本机、可信非串谋离线、合法归一化P输入假设仍适用。

最小干净检出：`python3 scripts/replay_clean.py --application --nodes 16 --secure-steps 8`。随机新工作目录不复制历史私有材料，保留全部新旧账本；这验证结构，不重跑96轮效果。

协调器不解析两方模型或结果份额：src.role_io独立角色进程完成检查点尾部选择、输入编排和自身目标份额导出，审计拒绝其他角色与V目录；协调器只得到公开状态。服务器共享模型资产以同角色硬链接传递。即使没有调用恢复，单一协调进程加载双方秘密仍会形成过宽视图，旧原型的这种读取已移除。

### 前向范围衔接修复

64节点第35轮旧state16拒绝，已保存失败证据。当前唯一配置改为operand_bounds_real，删除旧指数字段：state=24、score=32，其他界等值转换。src.ranges推导固定单位和最小包围位宽，非二次幂使用完整有符号秘密比较验证[-radius,radius)；不把32包围域误当24精确域。传播行L1限额21845、转置特征后向限额524287，守卫在线执行；state24也会拒绝更大的模型状态，不是通用无界训练。指数差分在±32分数下仍远小于32位有符号界，clip8及所有近似/截断值不变。FSS的k由包围位宽推导并检查，未固定为17。

旧范围政策的模型文件保留，但配置绑定拒绝在新政策下直接加载。原训练参数份额可继续更新并用新材料重新发布，不恢复参数、不添加兼容格式。公开数值配置也纳入握手，不只比较消息计划。默认授权目标为固定测试划分的第一个公开编号，选择不读取标签；手动prepare --target 35仍可指定。
