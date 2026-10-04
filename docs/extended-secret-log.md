# 扩展秘密对数

入口 `python3 verification/extended_log.py`，实现 src/operators.py:negative_log；独立整数参考 src/numerical.py:negative_log_reference。损失/训练可显式选择 loss_mode=range_reduced，默认quarter_taylor保持既有主链路兼容数值结果；它是同一loss算子的公开算法选择，未建立另一套配置。degree继续取唯一config的log_degree=8。

对f12概率单位q，秘密比较证明1≤q≤4096，只打开整批有效标志。零、负数及超过4096拒绝，不钳位。A2B取得全32位，按公开固定12…0顺序计算leading_j=bit_j AND NOT seen；所有位置都执行，将one-hot最高位转算术共享。秘密q乘单位leader不截断，再按公开常数2^max(0,11−j)累加得到u，按公开j权重累加得到秘密k。k、leader和q均不打开，u∈[2048,4096]，k≤11。

输出近似 −ln(q/4096)=k*ln2 + Σ_{j=1}^8 (1−u/4096)^j/j。ln2采用公开 round(4096 ln2)=2839，幂乘法及系数乘法都使用既有精确floor截断；整个结果保持32位/f12。q×leader≤4096，归约后的u≤4096，v≤2048，幂乘积和系数乘积≤2^23，不超有符号环；最大对数约8.318，也在当前loss/convergence范围内。这个界依赖输入正概率验证，不能用于检测输入之前发生的回绕。

Taylor实数截尾≤(1/2)^9/(9*(1−1/2))，外加ln2、系数和逐次floor误差；4096单位枚举报告实际最大误差。已有安全乘法、A2B/B2A和比较协议按固定电路组合实现此算子；不是复用第三方log库或精确实数log协议。梯度明确继续采用近似标准p−y，而非近似概率与该损失函数的精确导数。

训练入口 `python3 verification/training.py --indexed --extended-log` 运行真实共享前向、损失、梯度和更新，逐项对照选择同一loss_mode的定点参考。当前有效初始化的三轮loss与旧版恰好逐位相同，不证明所有初始化损失相同。60组网格用于秘密损失定义域覆盖，不等于60组完整训练成功；所有类别概率量化为0仍是训练阻塞，尤其类别数增大时。f12及已验证范围不能直接推广到更高精度。

实际4096单位、60组初始化均通过。独立60位Decimal高精度对照的最大绝对误差0.0019039560401546793；旧3组低于1/4的拒绝均解除，零等非法输入仍拒绝。有效初始化的三轮真正共享更新逐项通过，详细结果results/extended-log/summary.json和results/continuation/training-extended-log.json。
