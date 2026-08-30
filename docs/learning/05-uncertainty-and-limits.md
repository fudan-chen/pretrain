# 05 · 敏感性不是置信区间

## 本章问题

页面已经有一个阴影范围，为什么仍然不能写“显著领先”？

因为“有一个范围”不等于“这个范围具有统计覆盖率”。

## 当前实现了什么

当前 baseline 每个百分位只有四个 rung。v2 依次省略一个 rung，重新拟合 Hero 预测，并把四次预测的最小值/最大值记为：

```text
leave-one-rung-out sensitivity envelope
```

它适合回答：

- 结果是否被某一个 rung 强烈支配？
- 省略 d2048 时外推会移动多少？
- 当前 residual 的方向是否对 rung 选择敏感？

它不能回答：

- 真值有 95% 概率落在范围内吗？
- 多次重复实验中这个范围有 95% 覆盖率吗？
- 实测和预测差异是否具有统计显著性？

## 不确定性的来源

### 1. Rung 数量

只有四个尺度，而且 Hero compute 远大于各 rung。外推距离越远，对 `alpha` 的微小变化越敏感。

### 2. 固定渐近项

当前固定 `asymptote=1.5`。它是方法先验，不是由四个点自由估计。改变渐近项会改变外推。

### 3. d2048 未完成

85%–100% 的 d2048 是用 60%–80% 线性外推并加 0.005 correction 得到。它不是实测终点。

### 4. Metric 与评测噪声

Paloma macro 是 held-out aggregate。单次 eval 的采样波动、domain 构成与评测实现也会影响比较。

### 5. Regime 变化

Baseline 假定 Hero 与 Ladder 在可比 recipe 下运行。Context length、datamix、token budget 或关键训练 recipe 改变后，必须新建或分段 baseline。

### 6. W&B 数据采样

当前公开时序使用 `sampledHistory`。它可能不足以支撑“从未出现短时异常”之类全称命题。

## 用词规则

| 当前证据 | 可以写 | 不应写 |
|---|---|---|
| 只有点预测 | 高于/低于点预测 | 显著领先/显著落后 |
| 有 LOO envelope | 对 rung 选择较稳健/敏感 | 95% 置信区间 |
| 有 recipe 冲突 | 当前 baseline 可能不适用 | 仍在同一轨道 |
| 数据陈旧 | 最后一次观测为… | 当前正在… |
| 吞吐稳定 | 未见持续吞吐恶化 | 通信不是瓶颈 |

## 下一步如何变得更严谨

建议依次增加：

1. 报告 log-excess fit residual，而不把它伪装成预测 CI。
2. 对不同 asymptote 和 d2048 处理做方法敏感性矩阵。
3. 若能获得可重复评测或合理采样模型，再定义 bootstrap 或预测区间。
4. 做 leave-one-rung-out 的历史回测：用小 rung 预测被省略 rung。
5. 对 Paloma 16 domains 分别追踪，避免 macro 掩盖偏科。
6. 明确 recipe regime 切换点，禁止跨 regime 无条件比较。

## 一个好的结论模板

> **OBSERVED**：step 32,999 Paloma macro 原始值 = 2.2781243324279785。
> **DERIVED**：matched-progress point prediction = 2.3465101574845844，canonical residual = -0.06838582505660584。
> **SENSITIVITY**：LOO envelope 已报告，但不是置信区间。
> **INFERRED**：当前点估计没有显示弱于参考；对终点与显著性证据不足。
