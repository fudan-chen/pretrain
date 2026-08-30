# 02 · Scaling law 不是 learning curve

## 本章问题

一个公式如果能预测“不同模型规模在训练终点的 loss”，能否把 compute 换成当前累计 compute，从而预测同一个大模型的整条训练曲线？

通常不能。这里混淆了横截面规律和纵向轨迹。

## 两类完全不同的问题

### 横截面 Scaling Law

在相同训练百分位 `g` 上，比较不同宽度的 rung：

```text
d768  @ g% → (compute, Paloma loss)
d1024 @ g% → (compute, Paloma loss)
d1536 @ g% → (compute, Paloma loss)
d2048 @ g% → (compute, Paloma loss)
```

然后拟合：

```text
L(C) = 1.5 + A_g · C^(-alpha_g)
```

注意下标 `g`：每个训练百分位都有自己的 `A_g` 和 `alpha_g`。

### 纵向 Learning Curve

固定一个模型，观察它随 step 的 loss：

```text
Hero step 3k → loss
Hero step 6k → loss
Hero step 9k → loss
...
```

它受到 warmup、optimizer、batch、数据阶段、context length、checkpoint 恢复和评测 cadence 等因素影响。它不是把终点的 `A_100/alpha_100` 套在 `C_full × progress` 上就自然得到的。

## 一个直观类比

横截面问题像是：

> 同样学完课程 50% 时，不同基础的四个班考多少分？据此预测第五个班。

纵向问题像是：

> 第五个班从开课到结课，分数随每一周如何变化？

“结课时不同班级之间的规模规律”不能自动变成“某一个班每周的成长曲线”。

## 旧版为什么会错

旧版使用固定终点参数：

```python
c = C_full_hero * step / hero_steps
loss = 1.5 + A_terminal * c ** (-alpha_terminal)
```

这段代码在代数上可以执行，却回答了一个没有被 Ladder 实验注册的问题。结果在 step 32,999 给出约 2.21083，而正确的同进度参考约 2.34651。

实测 2.27812：

```text
旧 baseline：2.27812 - 2.21083 = +0.06729
v2 baseline：2.27812 - 2.34651 = -0.06839
```

方向完全反转。

## 官方逐 5% 方法

Marin 固定脚本在 5%、10%、…、100% 的每一个百分位重新拟合四个 rung，然后把同百分位 Hero compute 代入。非 5% 的 Hero eval，v2 只在相邻两个 Hero 点预测之间插值。

因此，正确数据结构不是一组全局系数：

```json
{"A": 87.1, "alpha": 0.0894}
```

而是一张方法表：

```text
5%   → A_5,   alpha_5,   hero_prediction_5
10%  → A_10,  alpha_10,  hero_prediction_10
...
100% → A_100, alpha_100, hero_prediction_100
```

## 看到“全程预测曲线”时的检查表

1. 曲线的每个点是否来自同一实验定义？
2. 终点 fit 是否被未经验证地扩展到中途？
3. 对比双方是否为相同 metric、dataset 和评测协议？
4. Recipe/context/datamix 改变后 baseline 是否重置？
5. 图中曲线是测量、插值还是外推？是否有清楚标记？

## 尚不能得出的结论

即使 matched-progress residual 为负，也不能直接推出：

- 终点一定达到 2.04；
- 训练显著领先；
- 后续 phase 改变仍保持同一 residual；
- 训练 loss 也相对 Ladder “领先”。
