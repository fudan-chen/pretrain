# 04 · 完整案例：step 32,999 的方向为什么会反转

## 问题

最新可比较的 Hero eval 为：

```text
step = 32,999
eval_dropless/paloma/macro_loss = 2.2781243324279785
total_steps = 390,251
```

它相对 Scaling Ladder 参考究竟更好还是更差？

## 第一步：确定进度

```text
progress = 32,999 / 390,251
         = 0.0845583995941
         = 8.45583995941%
```

这个点位于 5% 和 10% 之间。

## 第二步：取两侧官方点预测

```text
prediction_5%  = 2.3920926134624465
prediction_10% = 2.3261427192062980
```

## 第三步：只对 Hero 点预测插值

插值权重：

```text
w = (8.45583995941% - 5%) / (10% - 5%)
  ≈ 0.69116799188
```

所以：

```text
prediction = prediction_5% + w × (prediction_10% - prediction_5%)
           = 2.3465101574845844
```

注意：这里不插值 `A/alpha`，也不重新用终点 fit。

## 第四步：计算 residual

本项目定义：

```text
residual = actual - point_prediction
```

代入：

```text
residual = 2.2781243324279785 - 2.3465101574845844
         = -0.06838582505660584
```

Loss 越低越好，因此负 residual 表示实测低于点预测。

合格表述是：

> step 32,999 的 Paloma 实测比 matched-progress 点预测低约 0.0684。

如果只使用页面显示的五位小数 `2.27812`，会得到近似值 `-0.06839016`。它适合手算展示，但 canonical residual 必须使用 evidence 中未截断的原始浮点值。

## 旧版发生了什么

旧版用终点系数构造所谓“全程预测”：

```text
C_current = C_full × step / total_steps
prediction_old = 1.5 + A_terminal × C_current^(-alpha_terminal)
               ≈ 2.21083
```

于是：

```text
2.27812 - 2.21083 ≈ +0.06729
```

旧日报据此写“高于预测”。代数本身没有大错，错误是把终点横截面 fit 当成了时间曲线。

## 为什么这个案例值得保留

它展示了四个通用教训：

1. 同一份数据可以因 baseline 定义不同而得到相反结论。
2. 单元测试不能只测“函数能运行”，必须固定方法学 fixture。
3. 漂亮图表会放大方法错误，因为读者更容易相信视觉上的完整曲线。
4. 页面应渲染派生 Claim，而不是在 JavaScript 中临时推导科研结论。

## 测试如何防止复发

`tests/test_ladder.py` 固定：

```python
self.assertAlmostEqual(prediction, 2.3465101574845844, places=12)
self.assertAlmostEqual(residual, -0.06838582505660584, places=12)
```

未来任何改动只要再次把方向算反，CI 就会失败。

## 尚不能说什么

负 residual 不等于：

- 统计显著领先；
- 终点确定优于 2.04；
- 未来 recipe 改变后仍可沿用此 baseline；
- 每个 Paloma domain 都同步改善。
