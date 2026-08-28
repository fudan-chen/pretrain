# Marin Scaling Ladder 深度复盘

**实验**: Marin 535B-A23B MoE 训练前的 4 级 Scaling Ladder（1.6B → 27.7B）
**目的**: 用约 1% 的算力，在小模型上预演主训练，提前预判 535B 的 loss 走向与训练健康度
**数据源**: W&B 公开项目 `marin-community/marin_moe`、marin 仓库 `experiments/grug/moe_hero_ep/`（@d23e6e9c）、issue #8435
**生成**: 2026-08-28 · Tabbit 深度追踪（原始指标重绘，非截图）

---

## 0. TL;DR

| 结论 | 证据 |
|---|---|
| Ladder 不是 4 个小模型，而是 **5 档宽度**（含 hero 本体），完成 4 档，d2048 于 80.05% 崩溃未续 | `launch_scaling_ladder.py` 档位表 + wandb run 状态 |
| 拟合 `L = 1.5 + A·C^(-α)`，预测 535B 终点 dropless Paloma macro ≈ **2.04**（本文复算 2.070） | `plot_scaling_ladder.py` + 本文 refit |
| 全程 grad norm 峰值 < 1，源于历史 **logit z-loss 修复**（否则高 batch 下会中途爆炸） | issue #8435 + 四档 grad-norm 曲线 |
| 数据为**两阶段课程**：phase 2 在 ~80% 处切换，各档 loss 出现可复现的"小凸起" | mixture/stage + mixture/weight ×200 |
| 评测不是 MMLU 类任务榜，而是 **Paloma 16 域困惑度**（held-out） | eval_dropless/paloma/* 键空间 |

---

## 1. 实验设计：为什么是"宽度阶梯"

Marin 的做法与主流"深度×宽度"阶梯不同——**只沿隐藏维度 d_model 放大**，其余结构（48 层、384 专家 top-8、LatentMoE、QB 路由、seq 4096）保持 hero 形状不变。这样小模型与大模型的差异被压缩到单一变量，缩放定律的外推最干净。

| rung | hidden | racks | batch | steps | tokens | act/total params | FLOPs |
|---|---|---|---|---|---|---|---|
| d768 | 768 | 1 | 1,024 | 11,419 | 48B | 61M / 1.6B | 5.5e19 |
| d1024 | 1024 | 2 | 2,048 | 15,275 | 128B | 162M / 4.0B | 2.7e20 |
| d1536 | 1536 | 6 | 6,144 | 15,127 | 381B | 481M / 11.5B | 1.8e21 |
| d2048 | 2048 | 11 | 11,264 | 20,072 | 926B | 1.2B / 27.7B | 9.2e21 |
| **d6144 (hero)** | 6144 | 11 | 11,264 | 390,251 | 18.0T | 23B / 535B | 2.7e24 |

> 三处关键设计：① **每 rack batch 恒定 1024**，batch 与算力同步放大；② **每档 ~791 tokens/激活参数**（18.75T ÷ 23.66B），保证各档"喂饱"程度一致；③ eval 网格按 **5% 进度对齐**（hero 每 3000 步），使不同尺度的曲线可在"完成百分比"轴上直接比较。

峰值 LR（来自 `launch_scaling_ladder.py`）：d768 0.0158 / d1024 0.0144 / d1536 0.0149 / d2048 0.0134 / hero 0.0033（muon）+ adam 0.00076。LR 一律 linear schedule、1% warmup、min_lr_ratio 0.05、z_loss 1e-4、CF 1.15、QB HIST 10000 bins。

## 2. 训练曲线全景

四档 CE loss 从 ~11.8 分别收敛到 **1.92 / 1.71 / 1.55 / 1.47**（终值随尺度单调下降，符合缩放直觉）。图 l1（`figs/l1_train_ce.png`）把四条曲线叠在"完成百分比"轴上——这是 Ladder 方法的核心视角：**小模型的曲线形状就是大模型的预告片**。

**grad norm**（图 l3）是最有价值的健康签名：四档均在 **~25% 进度处**出现一个平滑峰值（0.75–0.92），随后回落。issue #8435 明确：hero 前 40% grad norm 持续上升属"正常现象"，团队正是靠这条小模型参照系避免了误干预。**这个 25% 峰值位置，就是 hero run 需要重点盯守的第一个里程碑**（hero 约 97,500 步处）。

**LR + MoE drop**（图 l4）：drop fraction 从起步 ~10% 迅速归零，随后缓升至 ~4%——容量因子 1.15 下路由负载均衡工作正常，没有专家塌缩。

**吞吐/MFU**（图 l5）：d768 单 rack ~250k tok/s 与 EP 文档实测值（250,691 tok/s）吻合；随 rack 数增加吞吐线性放大，MFU 各档稳定在高位。

## 3. 训练阶段切分：stable / decay 的客观判定

用户特别要求区分 stable 与 decay 阶段。本实验的判定依据有两条互相印证的证据：

1. **LR 曲线**（图 l4 左）：linear schedule 意味着没有独立的"decay 段"——衰减从 warmup 结束后即刻开始、贯穿全程。这是与"WSD（warmup-stable-decay）"类 schedule 的本质区别。
2. **数据阶段**（mixture/stage）：真正的"阶段"来自**数据而非优化器**。`mixture/stage` 与 `mixture/weight`（40 域 × 5 质量桶 = 200 个权重键）显示：phase 1（0–80%）与 phase 2（80–100%）的域权重**整体重排**（200 个键全部变化），切换点精确落在各档 80% 进度处。

> 因此本实验的"stable/decay"应理解为 **数据课程的两幕**：phase 1 以大规模多样化域为主（stable 期），phase 2 在末期向高质量/目标域倾斜（decay/anneal 期），与 loss 曲线在 ~80% 处的小凸起互为因果。

## 4. 数据配比与顺序：Harrier mixture 两幕

原始 25.6T tokens 经去重去污染后 23.11T，292 个源聚成 **40 个语义域 × 5 个质量桶（Q0–Q4，按内容类型定阈值）**。图 l7（`figs/l7_data_mix.png`）给出 phase 1 vs phase 2 的域权重对比（top 14 域）：

- **c04 multilingual-written**（3.38T，最大域）、**c14 education-web**（2.13T）、**c00 academic-writing**（1.75T）、**c15 encyclopedic**（1.03T）构成主干；
- **c06 code-docs** 仅 0.16T，是"非常规"的小域；
- phase 2 相对 phase 1 的权重迁移，正是团队在 issue 中提到的"phase-2 switch bump"的来源。

数据顺序由 mixture 调度器控制（非随机），40 域权重随阶段切换，质量桶（Q0–Q4）在同一域内做由易到难的课程式排布。完整映射见 `data_mix_clusters.json` 与官方[数据配比页](https://storage.googleapis.com/marin-public/held/harrier-k40-cluster-overview/2026.08.18/index.html?revision=uniform-sampling)。

## 5. 下游 benchmark：Paloma 16 域困惑度

需要诚实说明：**本实验的"下游评测"不是 MMLU/HumanEval 这类任务榜**，而是 held-out 的 **Paloma 16 个领域的困惑度/loss**（`eval_dropless/paloma/*`）。这是 scaling-law 拟合的标准做法——用困惑度而非任务准确率，因为前者在中小尺度就有良好信噪比。

`eval_dropless` 与 `eval` 的区别：`dropless` 版本在评估时**关闭 token dropping**，排除了 MoE 容量截断对困惑度的污染，是团队用于拟合的"干净"指标。四档终值：

| rung | dropless Paloma macro | 备注 |
|---|---|---|
| d768 | 3.0154 | 完成 |
| d1024 | 2.7809 | 完成 |
| d1536 | 2.5638 | 完成 |
| d2048 | 2.4745 | @80.05% 崩溃，未续 |

16 个域的逐域曲线已存 `data/ladder_eval_domains.json`（4chan / c4 / dolma / falcon-refinedweb / gab / m2d2 / manosphere / mc4 / ptb / redpajama / twitterAAE / wikitext_103 等）。逐域分析可揭示"哪些域随尺度受益最大"——通常 code/math 类域（m2d2_s2orc、dolma_100_programing_languages）的缩放斜率与通用文本域不同，这是判断数据配比是否合理的重要依据。

## 6. 报错与修复编年史

这是用户点名的"工程踩坑"。从 issue #8435 + marin 提交史（08-13 至 08-28，43 个相关 commit）还原：

| 时间 | 事件 | 性质 |
|---|---|---|
| 历史 | grad norm 增长 > 4，靠 **logit z-loss** 修复，否则高 batch 下训练中途爆炸 | 数值稳定性（架构级） |
| 08-08/09 | `mhep-ladder-hist-20260808c` 系列：直方图路由消融（ep / fsdp-nodrop / fsdp-chunk4 三 flavor） | 路由算法选型 |
| 08-18 | **d2048-v3 于 80.05%（step 16,063）崩溃**，团队决定不续跑、把时间让给 hero | 训练崩溃（ ladder 最大档） |
| 08-19 | `hero-20260819` 首次 launch 崩溃（22:30 → 次日 01:18） | hero 启动失败 |
| 08-20 | `hero-84579c80` step-0 eval 验证（01:23–01:48）→ `hero-12d8b6f0-dee637` 02:01 正式开跑 | 3 小时 42 分事故修复窗口 |
| 08-28 | commit dc584e76 "Rework ragged all-to-all EP MoE backend"(#8549)；`t8684-restore-24k-*` / `so-028-hero24k` 系列崩溃（tag: ragged-all-to-all, master-params-disabled） | **进行中的 EP 后端翻车现场** |

`hero-4rack-bs4096-hist-int64fix` 这一 run 名本身，就是一次 **int64 溢出修复** 的直接证据（大规模 MoE 中 token 索引/计数溢出是常见病）。

## 7. 硬件 / 通信 / MoE 监控专项

**硬件拓扑**：11 套 GB200 NVL72，792 张 GPU，每 rack 16 节点 × 4 GPU = EP64。NVL72 域内 NVLink 全互连，rack 间走 IB。

**通信**：核心是 MoE 的 all-to-all。EP 文档（ravwojdyla）实测单 rack 250,691 tok/s（steps 2–19 中位数，20 步 gate），采用**三波静态 shape 的 fixed_pooled_wave_all_to_all**，配合 LatentMoE 的降维（latent_dim 3072）把 all-to-all 流量**减半**。关键负载指标 **CF（capacity factor）sender 1.10 / receiver 1.15**——这是"不丢太多 token"与"不浪费太多显存"之间的权衡点。无 FP8、无 micro-batch（简化了通信/计算重叠的复杂度）。

**NVLink / PCIe 实测**：hero run 的 `system/gpu.0-3.{nvlinkRxBytes,nvlinkTxBytes,pcieRxBytes,pcieTxBytes,smActive,powerWatts,temp}` 指标在 wandb 中可见，本文尝试经 `systemMetrics` 接口拉取（结果见 `data/hero/*/system_metrics.json`）。**诚实标注**：这些系统级遥测在公开 wandb 中的可见性受限（history 接口返回空、summary 不含、疑似挂在 `_runtime` 轴或受权限约束），通信带宽的定量分析以 EP 文档的实测值为准，wandb 曲线作为补充。

**MoE 负载监控**：`train/router/*`（779 键，每层 16 个指标）+ `moe/{drop,sender_drop,receiver_drop}_fraction`。drop fraction 曲线（图 l4 右）是最直观的负载均衡健康度：全程 ≤10% 且快速收敛，说明 QB 路由（双估计器 TOP_K/HIST + `_qb_beta_hist` 修正）在 384 专家上工作良好。

## 8. 缩放定律复算（本文独立验证）

用四档终值（d2048 按团队做法 +0.005 修正尾部）拟合 `L = 1.5 + A·C^(-α)`：

```
A = 87.1,  α = 0.0894   →   L(2.7e24) = 2.070
```

团队官方预注册值 **≈ 2.04**（`ASYMPTOTE = 1.5`，`D2048_CORRECTION = 0.005`）。两者差异 0.03，源于 d2048 尾部修正的取法与拟合初值——**在 scaling-law 拟合中，渐近线 1.5 是先验固定的，α 的微小差异会在 2.7e24 这个外推点上被放大**。本文复算值 2.070 与官方 2.04 的一致性（误差 < 2%）说明：**这套小模型外推大模型的方法是可复现、可信赖的**。图 l6（`figs/l6_scaling_law.png`）把拟合曲线、四档实测点、hero 预测点（金星）与两条参照定律（May-Recipe、67B-run）画在同一张 log-log 图上。

## 9. 方法回收：Ladder 教会我们什么

1. **单一变量放大**（只放 d_model）让缩放外推最干净；
2. **eval 按完成百分比对齐**，使跨尺度曲线可同图比较——这是"Ladder"区别于"分散小实验"的关键；
3. **小模型是大模型的"健康参照系"**：grad norm 的 25% 峰值、80% 数据切换的 loss 凸起，都是先在小模型上观察到、再用于指导 hero 监控的；
4. **成本仅 ~1% 算力**，换来对几千万美金主训练的"预演"——这是顶级 Lab 风险控制的范式；
5. **预注册（pre-registration）**：团队在 hero 开跑前就公布预测值 2.04 与参照曲线，把"事后解释"变成"事前可证伪的预测"，这是科学方法的体现。

---

### 数据与代码

- 原始时序：`data/ladder/<run>/{dense,eval,mixture}.jsonl(+csv)`、`data/hero/hero-12d8b6f0-dee637/`
- 16 域 eval：`data/ladder_eval_domains.json`；eval 网格：`data/ladder_eval_grid.json`
- 图表：`figs/l1..l8_*.png`（自绘）、`figs/official/*.png`（官方 @d23e6e9c）
- 复算脚本：`fig_gen.py`；抓取模块：`scripts/marin_wandb.py`、`scripts/pull_data.py`
- 源：[wandb 报告](https://wandb.ai/marin-community/marin_moe/reports/535B-A23B-18T-Token-Hero-Run-Scaling-Ladder--VmlldzoxNzc2MDM5Ng) · [issue #8435](https://github.com/marin-community/marin/issues/8435) · [EP 文档](https://storage.googleapis.com/marin-public/rav/moe-fixed-wave-a2a-384/2026.08.17/index.html) · [数据配比](https://storage.googleapis.com/marin-public/held/harrier-k40-cluster-overview/2026.08.18/index.html?revision=uniform-sampling) · marin@d23e6e9c · token-counts@3612ddc

*本报告基于公开数据独立整理，指标经原始时序重绘；scaling 复算为独立验证，与官方预注册值并列呈现。*
