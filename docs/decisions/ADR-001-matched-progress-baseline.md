# ADR-001：采用 matched-progress baseline

- 状态：Accepted
- 日期：2026-08-30
- 方法版本：`marin-matched-progress-v1`

## 背景

v1 把 100% 终点 cross-rung fit 的系数应用到 `C_full × current_progress`，把横截面 scaling law 当成纵向 learning curve，导致 step 32,999 的 residual 方向翻转。

## 决策

1. 每 5% 训练进度跨 d768/d1024/d1536/d2048 单独拟合固定渐近项幂律。
2. d2048 85%–100% 使用官方 60–80% 线性外推 +0.005。
3. 非 5% Hero eval 只在相邻 Hero 点预测之间线性插值。
4. `<5%` 返回 unavailable；`>100%` 返回越界。
5. 报告 leave-one-rung-out sensitivity，但明确不是 confidence interval。

## 后果

- v1 的“全程预测曲线”不能迁移到 v2。
- Dashboard 只能把 Paloma 与同口径 baseline 画在同一图。
- Train CE 单独展示。
- 任何 recipe regime 改变都必须检查 baseline applicability。

## 固定验收

```text
5% = 2.3920926134624465
10% = 2.3261427192062980
100% = 2.0387845986743045
step 32999 residual < 0
```
