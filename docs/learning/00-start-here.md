# 00 · 从这里开始：这个项目到底在回答什么

## 本章问题

面对一个正在公开训练的 535B MoE，哪些问题可以由公开数据回答？哪些问题即使有漂亮图表也回答不了？

## 先记住四个问题

首页只应该回答：

1. 最后的公开证据是否足够新？
2. Run 处于什么 recipe、阶段和训练进度？
3. 同口径 eval 相对同进度参考更高、更低，还是暂时不可比较？
4. 最近出现了什么可验证变化？

如果一个页面先讲架构故事、性能结论或“走势很好”，却没有先回答数据时间和比较口径，应先降低信任。

## 三层数据，一层叙事

```text
外部公开源
  ↓
evidence：尽量保留原始记录、查询状态与 checksum
  ↓
derived：用固定算法从 evidence 生成，可全部重建
  ↓
claims：给每条结论标记 OBSERVED / DERIVED / INFERRED
  ↓
site / reports：只负责呈现，不在页面里重新推导
```

### Evidence

- `data/snapshots/`：`main` 已有的 GitHub、Hugging Face、官网证据快照。
- `data/hero/<run>/`：W&B run meta、dense、eval、router、mixture 与系统时序。
- `data/ladder/source/*.jsonl`：四个 rung 经 W&B `sampledHistory` 返回的源记录。
- `data/ladder_eval_grid.manifest.json`：run、采样、归一化与 checksum 清单。
- `data/ladder_eval_grid.json`：从上述源记录选择出的逐 5% Paloma 输入。

Evidence 不等于“完整真相”。当前 W&B 时序来自 `sampledHistory`，因此 v2 明确标记 `complete_history=false`，不能假装每一个瞬时尖峰都被保留。

### Derived

- `data/baselines/matched_progress_v1.json`：每 5% 的 scaling fit 与 Hero 点预测。
- `data/derived/current_status.json`：当前 run 状态、同口径比较和用于绘图的序列。
- `data/derived/claim_ledger.json`：机器可读结论账本。

Derived 文件可以删除后重建；它们不应被当成不可变原始证据。

### Presentation

- `site/`：v2 自包含静态学习站点；课程和日报会被渲染到站点内部，当前 Claim 所需 evidence 会复制到 `site/artifacts/`。
- `reports/generated/hero/`：纠正版 Hero 日报。

旧版 `dashboard/` 与 `reports/daily/` 不被覆盖，便于学习者比较错误是如何进入图表和文字的。

## 一条命令开始

```bash
python scripts/track_hero.py build
python -m unittest discover -s tests -v
```

`build` 不访问网络，只用仓库内已有证据重建 baseline、status、claims、v2 日报和站点。`update` 才会先刷新公开 W&B 数据。

如需主动刷新四个 rung 的采样 evidence，使用单独的网络命令 `python scripts/collect_ladder_grid.py`。这不是普通 `build` 的一部分；由于来源是 server-sampled history，新采集是一份新证据，不承诺与旧 checksum 完全相同。

预期关键输出：

```text
terminal prediction ≈ 2.03878460
step 32999 canonical residual ≈ -0.06838583
```

## 你应该能回答的自测题

1. 页面写 “run state=running” 是否等于此刻仍在训练？
2. 为什么构建时间不能替代 `data_as_of`？
3. 为什么 `data/derived/` 应该可重建？
4. 旧页面为什么仍然保留？
5. 为什么 `sampledHistory` 的 JSONL 不能被称为完整逐步历史？

## 答案

1. 不等于。它只是最后一次 run metadata 中的状态，还要结合 heartbeat 和数据时间。
2. 重新构建旧数据会产生新的构建时间，却不会让证据变新。
3. 因为只有原始证据与固定方法共同决定派生结果；否则就无法审计。
4. 错误路径是最好的反例。删除旧内容会损失方法演进的学习价值。
5. 因为采样由服务端决定；它能复查被返回的记录，却不能证明未返回的瞬时事件不存在。

## 当前阶段边界

v2 Phase 1 聚焦 Scaling Ladder、matched-progress、证据分层和可执行适用性门禁。Paloma 16 域、完整 Router 层间结构、datamix delta、系统瓶颈归因和事故因果链仍是待补分析；第 06 章对它们给出阅读边界，不代表这些分析已经实现。

## 尚不能得出的结论

- 不能仅凭公开采样数据证明训练没有任何短时异常。
- 不能仅凭当前 residual 保证最终达到 2.04。
- 不能仅凭吞吐稳定证明 all-to-all 不构成瓶颈。
- 不能把 issue 中的计划描述自动当成当前 run 的实际配置。
