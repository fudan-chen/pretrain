# 指标词典

机器可读版本见 `registry/metrics.json`。

| metric key | 数据集/总体 | 单位 | 能比较 | 不能比较 |
|---|---|---|---|---|
| `train/cross_entropy_loss` | 当前训练 batch | nats/token，依实现 | 同 run 趋势、阶段、尖峰 | Paloma 绝对值、泛化结论 |
| `eval_dropless/paloma/macro_loss` | Paloma 16 域 dropless eval | macro loss | 同协议 rung、matched-progress | Train CE、不同 tokenizer/context 的无条件值 |
| `grad/norm/total` | 当前优化 step | norm | 同 run 尺度与形态 | 固定 2.0 即“异常”的跨阶段判断 |
| `optim/learning_rate` | optimizer 主组 | learning rate | run config 与曲线一致性 | 用曲线猜 schedule 后覆盖 config |
| `throughput/tokens_per_second` | 当前 job | token/s | 同 run 时间变化 | 不同 batch/硬件的简单排名 |
| `throughput/mfu` | 当前实现的模型 FLOPs 利用率 | percent | 同定义、同硬件变化 | 未统一 FLOPs 定义的跨 run 比较 |
| `moe/drop_fraction` | capacity-limited token routing | fraction | 同 recipe 变化 | 单独证明路由塌缩/健康 |
| `train/router/bias_max` | router aggregate | bias units | 同一 metric 趋势 | 与 overflow 共用无单位轴 |
| `train/router/capacity_overflow_rate_mean` | router aggregate | fraction | 同一 metric 趋势 | 当成 0.1–0.2% 的硬编码常量 |

## 三个特别容易混淆的概念

### Metric 名相近不等于同一统计量

`loss` 可能来自训练 batch、held-out dataset、dropless eval、macro average 或 micro average。比较前必须同时匹配 dataset、population、transform 和 unit。

### 缺失不等于零

采样时序中的缺点应断线或标记 unavailable，不能默认填 0，也不能跨长空窗连线制造平滑趋势。

### 稳定不等于因果解释

吞吐稳定只能支持“未观察到持续吞吐恶化”，不能单独支持“通信不是瓶颈”。
