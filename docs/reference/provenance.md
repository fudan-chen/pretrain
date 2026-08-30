# Provenance 与时间语义

## 从外部源到结论的链条

Ladder baseline 的 lineage 是：

```text
W&B sampledHistory
→ data/ladder/source/<rung>.jsonl + source_sha256
→ data/ladder_eval_grid.manifest.json
→ data/ladder_eval_grid.json + grid_sha256
→ matched_progress_v1.json + method_id/applicability
→ current_status.json
→ claim_ledger.json
→ site / reports
```

Hero 状态的 lineage 是 `meta/dense/eval/router/mixture` → status → claims。生态工程事件则继续使用 `track_marin.py` 的不可变 daily snapshots；Hero 报告不再实现一套简化且可能漏分页的 GitHub collector。

## 三个时间不能混用

| 字段 | 含义 | 用途 |
|---|---|---|
| `data_as_of` | 最后一条 metric 的观测时间 | 页面 freshness 的主依据 |
| `heartbeat_at` | 上游 run 最后心跳 | 判断 run metadata 是否仍更新 |
| `collected_at` | 外部采集发生时间 | 标识 evidence 版本，不证明 metric 在此时仍更新 |
| build time | 本地派生/渲染发生时间 | 运维审计，不证明数据新鲜 |

重新构建一份旧 evidence 只会更新构建时间，不会更新 `data_as_of`。

## Checksum

每个参与 Claim 的本地 artifact 都记录 SHA-256。它解决两个问题：

1. 复算时确认输入没有被悄悄替换。
2. 页面数值能回到具体 evidence 版本，而不是只指向一个浮动路径。

Rung bundle 还多一层 manifest：每个 source JSONL 有 hash，manifest 记录 grid hash，baseline 再记录 grid 与 manifest hash。任一层变化都应导致可审查的 provenance 变化。

## Sampling

Hero 与 Ladder 当前都使用 W&B `sampledHistory`，必须记录：

```text
provider = wandb sampledHistory
complete_history = false
```

若未来改用完整 scan，应更新 sampling contract，而不是仍沿用旧说明。

“source JSONL”只表示 collector 实际收到并固定下来的源记录；它不授权“训练从未发生未记录尖峰”这类全称结论。再次运行 collector 是采集一份新 evidence，不是对旧 evidence 的纯离线重放。

## Canonical precision

Provenance 不只追文件，也追数值生成方式：

- JSON 中未截断的 evidence/derived 浮点值是 canonical；
- 页面与日报可按固定小数位展示，但显示值不能成为下游输入；
- 公式、method ID 和输入 checksum 共同决定派生值；
- 同一 Claim 不应因 README、HTML 和 Markdown 各自手算而出现多个“高精度”结果。

例如 step 32,999 的 canonical residual 是 `-0.06838582505660584`；`-0.06839` 是显示值，使用显示 actual 手算出的 `-0.06839016` 只是近似演示。

## Baseline applicability provenance

“方法正确”不等于“当前 run 仍可比较”。Baseline 固定 requirements，status 保存每一项 selector、expected、observed 与 result：

```text
all match      → supported
any mismatch   → mismatch
any missing    → unverified
```

后两种状态都抑制 prediction/residual。这个 gate 的输出本身进入 Claim ledger，使“为什么没有比较”也可被审计。Recipe 改变时应注册新 regime 或新 baseline，不能改页面文字掩盖不适用。

## 发布副本

自包含站点把当前 Claim 依赖的 evidence 复制到 `site/artifacts/<repository-path>`，并在 `site/data/catalog.json` 中记录 path、checksum、provider 与 sampling。`site/evidence/<artifact-slug>/` 再提供人类可读的定位页；例如 issue Claim 会先显示 `number=8435` 和相关 excerpt 路径，而不是让读者在 1.3 MB JSON 中盲搜。预览可以截断，发布 artifact 与 checksum 才是复算权威输入；仓库输入和发布副本的 checksum 应一致。

## 来源优先级

`registry/sources.json` 固定：

1. runtime config / raw metric
2. pinned source code
3. issue/comment narrative
4. secondary analysis

优先级用于处理事实冲突，不用于抹掉低优先级来源。低优先级叙述仍可作为意图与背景证据。

## Phase 1 的 provenance 缺口

- `sampledHistory` 不是完整 scan；
- 当前统计范围是 LOO 方法敏感性，不是概率区间；
- Paloma domain、全层 Router、datamix 与事件因果链还没有对应的完整 Claim lineage；
- JSON Schema 对跨文件 checksum 和语义关系的覆盖仍不完整，关键门禁依赖 Python validator 与测试。

这些是公开边界，不应用“可审计”一词把它们隐藏起来。
