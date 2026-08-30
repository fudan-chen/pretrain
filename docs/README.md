# 文档地图

这套文档不是按代码文件排序，而是按“理解一个公开大模型训练追踪系统需要哪些前置知识”排序。

## 推荐路径

| 读者 | 建议入口 | 目标 |
|---|---|---|
| 第一次来 | [`learning/00-start-here.md`](learning/00-start-here.md) | 5 分钟看懂项目边界与四个核心问题 |
| 想学方法 | [`learning/02-scaling-law-is-not-learning-curve.md`](learning/02-scaling-law-is-not-learning-curve.md) | 理解本次错误为什么不是“小数算错” |
| 想复算 | [`learning/03-reproduce-official-ladder.md`](learning/03-reproduce-official-ladder.md) | 从公开采样 evidence 追到 grid，再重建官方预测 |
| 想审查结论 | [`learning/01-evidence-derived-inference.md`](learning/01-evidence-derived-inference.md) | 检查事实、计算和推断是否混在一起 |
| 想主动反证 | [`learning/07-falsification-lab.md`](learning/07-falsification-lab.md) | 注入 recipe mismatch 和 residual 反向案例 |
| 想维护 | [`maintainers/RUNBOOK_V2.md`](maintainers/RUNBOOK_V2.md) | 构建、验证、双跑和发布 v2 |
| 想比较旧版 | [`comparison/v1-v2.md`](comparison/v1-v2.md) | 对照旧方法、旧展示和 v2 的改动 |

## 八章课程

1. [`00-start-here.md`](learning/00-start-here.md)：项目与证据边界。
2. [`01-evidence-derived-inference.md`](learning/01-evidence-derived-inference.md)：三层 Claim 模型。
3. [`02-scaling-law-is-not-learning-curve.md`](learning/02-scaling-law-is-not-learning-curve.md)：横截面 scaling law 与纵向 learning curve。
4. [`03-reproduce-official-ladder.md`](learning/03-reproduce-official-ladder.md)：忠实复现官方逐 5% 方法。
5. [`04-worked-example-step-32999.md`](learning/04-worked-example-step-32999.md)：符号反转的完整案例。
6. [`05-uncertainty-and-limits.md`](learning/05-uncertainty-and-limits.md)：敏感性、不确定性与语言边界。
7. [`06-reading-training-signals.md`](learning/06-reading-training-signals.md)：训练、路由与系统指标怎么读。
8. [`07-falsification-lab.md`](learning/07-falsification-lab.md)：把适用性失配和方向翻转变成可执行反证实验。

## 查阅资料

- [`reference/architecture.md`](reference/architecture.md)：代码与数据流。
- [`reference/metric-dictionary.md`](reference/metric-dictionary.md)：每个指标的单位、可比性与误读。
- [`reference/data-contracts.md`](reference/data-contracts.md)：baseline、status 和 claim JSON 契约。
- [`reference/provenance.md`](reference/provenance.md)：路径、checksum、采样与三个时间概念。
- [`decisions/ADR-001-matched-progress-baseline.md`](decisions/ADR-001-matched-progress-baseline.md)：为什么采用 matched-progress。
- [`decisions/ADR-002-claim-status-model.md`](decisions/ADR-002-claim-status-model.md)：为什么页面只能渲染 typed claims。
- [`decisions/ADR-003-baseline-applicability-gate.md`](decisions/ADR-003-baseline-applicability-gate.md)：为什么 recipe 可比性必须是可执行门禁。

## v2 Phase 1 的边界

当前 Phase 1 已闭合这条主路径：公开 rung 采样 evidence → 5% grid → matched-progress baseline → recipe 适用性门禁 → Hero status/claims → 自包含学习站点。重点是修正 Scaling Ladder 方法、建立证据分层，并证明错误结论能被自动抑制。

以下内容仍是后续阶段，不应从当前站点中反向推断已经完成：Paloma 16 域归因、完整 48 层 Router heatmap、datamix phase delta/JSD、事件因果链、完整 W&B scan、统计预测区间，以及生产 schedule/Pages 切换。Phase 1 的 `sampledHistory` 与 leave-one-rung-out 范围也分别不等于完整历史和置信区间。

## 历史材料

旧版 `dashboard/`、`reports/daily/`、`reports/ladder/` 和 `docs/OPERATIONS.md` 暂时保留。它们是 v1 对照材料，不是 v2 的权威说明。三条原远端分支也没有在本次重构中删除或覆盖。
