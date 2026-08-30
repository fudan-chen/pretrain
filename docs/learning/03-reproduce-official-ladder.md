# 03 · 从公开 rung evidence 复现 Scaling Ladder

## 本章目标

从四个公开 W&B rung 采集 Paloma evidence，生成 5% grid，再用固定的官方 FLOPs 常数重建：

```text
5%   Hero prediction = 2.3920926134624465
10%  Hero prediction = 2.3261427192062980
100% Hero prediction = 2.0387845986743045
```

## 固定来源

- 上游 commit：`d23e6e9c3673435fb82d83aa6c51a607d0da6009`
- 上游脚本：`experiments/grug/moe_hero_ep/plot_scaling_ladder.py`
- 固定渐近项：`1.5`
- d2048 correction：`+0.005`
- Compute 口径：training FLOPs excluding `lm_head`

固定 commit 很重要。使用浮动 `main` 会让今天和下周的“同一方法”可能不是同一份代码。

## 第零步：从公开 rung 建立 evidence

```bash
python scripts/collect_ladder_grid.py
```

这一步按官方脚本固定的四个 display name 定位 run，读取
`eval_dropless/paloma/macro_loss`，并保存：

```text
data/ladder/source/{d768,d1024,d1536,d2048}.jsonl
data/ladder_eval_grid.manifest.json
data/ladder_eval_grid.json
```

Manifest 记录 run ID、状态、heartbeat、`stop_after_steps`、采样方式与每个 artifact 的 SHA-256。Collector 请求每个 run 最多 100,000 个样本；当前实际返回 16–21 条稀疏 eval 记录。来源仍是 W&B `sampledHistory`，所以这是可重采的公开采样 evidence，不声称是完整逐步历史。

这里要区分两种复现：

- **离线复算**：从仓库已经固定的 grid、manifest 和 checksum 重建 baseline，结果应逐位通过 fixture。
- **重新采集**：再次访问 W&B，形成一份新的采样 evidence。上游记录或服务端采样可能变化，因此应审查 Git diff 和新 manifest，而不是要求新旧文件天然同 SHA。

`collect_ladder_grid.py` 同时执行网络采集和 grid 归一化；普通 `build` 不会调用它。若采集中途失败，不要把部分刷新文件作为一组完整 evidence 发布，应重新运行并确认 manifest 中四个 rung 与 grid checksum 全部齐全。

## Rung 计算预算

| rung | steps | full compute，no lm_head |
|---|---:|---:|
| d768 | 11,420 | 2.649679880270119e19 |
| d1024 | 15,276 | 1.7261182741798453e20 |
| d1536 | 15,128 | 1.3813258500033133e21 |
| d2048 | 20,072 | 7.741814947656449e21 |
| d6144 Hero | 390,251 | 2.6108941613772703e24 |

报告中的 2.70e24 是包含或混合了其他口径的近似值，不能与 no-lm-head fit 混用而不解释。

## 第一步：把 eval step 对齐到 5% 网格

对每个 rung：

```text
fraction = round(round(step / total_steps × 20) / 20, 2)
```

如果多个 eval 落到同一百分位，v2 选择离目标 step 最近者；距离相同但值冲突则报错，不能静默用最后一条覆盖。

## 第二步：处理 d2048 未完成部分

d2048 在约 80% 后没有实测。官方方法用 60%、65%、70%、75%、80% 五点做线性拟合：

```text
loss(g) = slope × g + intercept
```

对 85%–100%：

```text
loss_pinned(g) = slope × g + intercept + 0.005
```

80% 本身仍使用实测值。100% 的 d2048 输入为：

```text
2.4087081241607664
```

## 第三步：每个百分位单独拟合

对 `g ∈ {0.05, 0.10, …, 1.00}`：

```text
C_rung(g) = C_full_rung × g
log(loss_rung(g) - 1.5) = intercept + slope × log(C_rung(g))
A_g = exp(intercept)
alpha_g = -slope
```

然后：

```text
C_hero(g) = C_full_hero × g
prediction_hero(g) = 1.5 + A_g × C_hero(g)^(-alpha_g)
```

关键拟合参数：

| progress | A | alpha |
|---|---:|---:|
| 5% | 67.5503005578 | 0.0812959384 |
| 10% | 57.6859276740 | 0.0787475508 |
| 100% | 84.7875932411 | 0.0899756766 |

## 第四步：报告方法敏感性

v2 在每个百分位对四个 rung 分别留一：

```text
omit d768  → fit three rungs → Hero prediction
omit d1024 → fit three rungs → Hero prediction
omit d1536 → fit three rungs → Hero prediction
omit d2048 → fit three rungs → Hero prediction
```

四个预测的最小值与最大值形成 `leave-one-rung-out sensitivity range`。它回答“外推对某个 rung 有多敏感”，不回答统计覆盖率，因此不是 confidence interval。

## 离线复算

```bash
python scripts/track_hero.py baseline
python -m unittest tests.test_ladder -v
```

输出文件：

```text
data/baselines/matched_progress_v1.json
```

每个百分位都保存：rung 输入、观测/外推状态、`A/alpha`、Hero compute、点预测和 LOO fits。

## 自测

1. d2048 的 100% loss 为什么不是 80% 最后一个观测值 `2.47450 + 0.005`？
2. 为什么 Hero 100% compute 必须是 `2.610894e24`？
3. 为什么 LOO range 不能写成 95% CI？

答案分别是：官方先对 60–80% 做线性外推；fit 明确排除 `lm_head`；LOO 不是一个有覆盖率定义的概率区间。
