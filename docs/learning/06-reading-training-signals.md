# 06 · 如何阅读训练、Router 与系统信号

## 本章原则

一个指标通常能证明“发生了什么”，却不能单独证明“为什么发生”。先定义 metric contract，再讨论解释。

## Train Cross-Entropy

Metric：`train/cross_entropy_loss`

适合观察：

- 同一 run 内的长期下降趋势；
- 阶段边界附近的跳变；
- 重启、坏 batch 或优化异常相关尖峰；
- 与 learning rate、grad norm 的时间对齐。

不适合：

- 与 `eval_dropless/paloma/macro_loss` 比绝对值；
- 直接判断泛化；
- 把一个下降曲线当成终点 scaling prediction。

## Paloma Macro Loss

Metric：`eval_dropless/paloma/macro_loss`

适合：

- 与同一评测协议下的 Ladder matched-progress 参考比较；
- 观察 held-out 能力随进度变化；
- 作为 macro 总览入口。

限制：

- Macro 会掩盖 16 个 domain 的偏科；
- 评测 cadence 比 train metric 稀疏；
- step 0 随机初始化值不应进入训练态 residual。

## Grad Norm

Metric：`grad/norm/total`

适合观察尺度、尖峰、阶段形态。官方 issue 提到 rung 的 grad norm 在约 25% 附近达到高点，这是一条经验参考，不是固定阈值。

因此：

```text
progress < 25% → 只能写“尚未到达参考区”
progress > 25% → 可以开始对照形态，但不能写“通过健康检查”
```

## Learning Rate

Metric：`optim/learning_rate`

页面对 schedule 的事实必须优先读取 run config。当前 meta 显示：

```text
lr_schedule = linear
warmup = 0.01
decay = null
```

Issue 或二手总结中的 cosine/WSD 叙述不能覆盖实际配置。曲线形状可以辅助验证，但不替代配置事实。

## Throughput 与 MFU

Metrics：

- `throughput/tokens_per_second`
- `throughput/mfu`

适合：

- 同一 run 内发现持续降速、重启或周期性抖动；
- 与系统事件和 checkpoint 时间对齐；
- 观察稳定区间。

不适合：

- 未统一 FLOPs 定义、硬件和 batch 时跨 rung 排名；
- 用“吞吐稳定”证明 all-to-all 不构成瓶颈；
- 不说明 MFU 是原始百分数还是 0–1 比例。

## MoE Drop 与 Router

Metrics：

- `moe/drop_fraction`
- `train/router/bias_max`
- `train/router/capacity_overflow_rate_mean`

Drop 反映受容量限制而丢弃的 token 比例。Router bias 和 overflow 是不同单位，不应画在无明确双轴实现的同一 y 轴上。

当前采集只覆盖 aggregate 和 layer 0/1/2/46/47 的选定指标，因此不能写“完整 48 层均无塌缩”。更好的后续分析是：

- 48 层 × step 的 heatmap；
- 每层 expert load entropy；
- overflow 的层间分位数；
- 持续时间与 change point，而非单点固定阈值。

## Datamix

`cXXqY` 是 40 个语义簇 × 5 个质量桶。公开定义中 Q0 是 Lowest、Q4 是 Highest。

判断 phase 变化应计算：

- 每个 cell 的 before/after/delta；
- 每个 cluster 聚合 delta；
- Q bucket 总占比；
- weighted mean quality bucket；
- Jensen–Shannon divergence。

“phase 2 更高质量”“从易到难课程”必须由这些量支持，不能从阶段编号或少数 domain 名称推断。

## 系统遥测

NVLink/PCIe 指标为累计 byte counter 或采样值时，首先要确认单位、重置语义和聚合维度。看到非零不等于通信健康；看到零也可能是 metric 缺失。

硬件表述应区分：

- 物理拓扑：11 个 GB200 NVL72 rack；
- run config：176 replicas × 4 devices = 704 configured device slots；
- “11 × 72 = 792”只是 rack 容量算术，不等于 job active device count。

## 事件分析模板

```text
现象
→ 时间窗与原始 metric
→ issue/comment
→ commit/PR
→ 是否部署进当前 run
→ 部署后指标变化
→ 替代解释
→ 置信度
```

只有“现象”和“某次提交时间接近”时，最多写相关，不写因果。
