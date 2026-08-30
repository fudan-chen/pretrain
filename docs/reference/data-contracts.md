# 数据契约

## Ladder source bundle

显式网络命令 `python scripts/collect_ladder_grid.py` 维护三层输入：

```text
data/ladder/source/<rung>.jsonl
data/ladder_eval_grid.manifest.json
data/ladder_eval_grid.json
```

四个 JSONL 保存 W&B `sampledHistory` 实际返回的 `_step`、`_timestamp` 和 `eval_dropless/paloma/macro_loss`。它们必须被描述为 `complete_history=false` 的采样源记录，不能称为完整逐步 history。

Manifest 必须记录：provider、entity/project、metric、采样请求、归一化规则、固定上游 commit/script、grid path/SHA-256，以及每个 rung 的 display name、run ID、状态、heartbeat、`stop_after_steps`、source path/SHA-256、采样行数和选中行数。Grid checksum 必须与 manifest 一致；缺任一 rung 时不得发布为完整输入。

重新联网采集产生的是一份新 evidence。由于上游或服务端采样可能变化，新旧 checksum 不必相同；维护者必须审查差异，而不是把“不相同”自动判为错误。

## Baseline

路径：`data/baselines/matched_progress_v1.json`

必须包含：

- `method_id`
- pinned upstream commit/script
- grid input path/SHA-256；存在 manifest 时同时记录 manifest path/SHA-256
- asymptote、d2048 correction、Hero steps
- 5%–100% 每个 fraction 的 rung 输入
- observed/extrapolated 状态
- `A/alpha`
- Hero point prediction
- LOO sensitivity fits 与范围
- machine-readable `applicability.recipe_regime_id/policy/requirements`

当前 applicability requirements 为：run ID、4096 context、注册训练步数、tracker group 和 Harrier datamix tag。Requirement 由 selector、operator 和 expected 组成；渲染层不能自行决定是否适用。

## Current Status

路径：`data/derived/current_status.json`

核心字段：

- `data_as_of`：最后一条数据时间，不是构建时间
- `run`：state、heartbeat、step、progress、regime
- `recipe`：从 meta 读取的 LR、设备，以及 `replicas × devices_per_replica` 得到的 configured device slots；它不等于瞬时 active/利用中的设备数
- `latest`：每个 metric 的最新值、step、时间
- `baseline_applicability`：`supported | mismatch | unverified`、逐项 observed/expected/result
- `matched_progress`：同口径实际值、点预测、residual、敏感性；门禁不是 `supported` 时必须为 `null`
- `milestones`：只由数据推导的 reached/not_reached
- `source_health` 与 `artifacts`

## Claim Ledger

路径：`data/derived/claim_ledger.json`

共同字段：

- `id`
- `kind = OBSERVED | DERIVED | INFERRED`
- `support`
- `statement`
- `as_of`
- `evidence`

附加规则：

- OBSERVED 必须有 evidence。
- DERIVED 必须有 derivation。
- INFERRED 必须有 confidence、alternative explanations、falsifiers 和 caveats。
- 没有 uncertainty method 时，不允许生成“显著”措辞。

Applicability 本身也生成 Claim：`supported` 才能支持 matched-progress；`mismatch` 对应 contradicted；缺字段造成的 `unverified` 对应 insufficient evidence。

## Canonical 数值与显示精度

机器 JSON 中未截断的数值是 canonical value；HTML、Markdown 和表格中的五位小数只是 display value。派生计算必须使用 evidence/baseline 中的 canonical 数值，禁止把页面文本解析回来继续计算。

step 32,999 的例子：

```text
actual canonical     = 2.2781243324279785
prediction canonical = 2.3465101574845844
residual canonical   = -0.06838582505660584
display              = 2.27812, 2.34651, -0.06839
```

用显示值相减得到的 `-0.06839016` 是手算近似，不是第二个权威 residual。测试、Claim 和下游计算必须使用 canonical value；面向读者的句子应说明舍入精度。

## Report Index

路径：`reports/generated/hero/index.json`

索引与 Markdown 详情必须来自同一份内存 manifest，避免列表与正文漂移。每条包括窗口、方法版本、窗口 stats 和可用的 matched-progress comparison。

日报中的原始 metric 点是 OBSERVED；窗口 `mean/max`、progress 和 residual 是 DERIVED。窗口结束时间、eval `observed_at`、全局 `data_as_of` 和构建时间含义不同，不能互相替代。

## Self-contained site bundle

`site/` 是发布边界，而不是一个依赖仓库父目录的预览壳：

- 学习 Markdown 渲染到 `site/learn/<slug>/index.html`；
- 日报 Markdown 渲染到 `site/daily/<name>/index.html`；
- 当前 Claim 所需 evidence 复制到 `site/artifacts/`；
- 派生 JSON 与 `catalog.json` 位于 `site/data/`。

所有站内链接解析后必须仍在 `site/` 内。`scripts/check_site.py` 将 path escape、缺页、缺 anchor、未替换 token 或无 title/desc 的数据 SVG 视为发布失败。

## 验证边界

`schemas/*.json` 提供公开结构说明；Phase 1 的关键语义约束同时由 `ladder.validate_baseline`、Claim validator、applicability gate 与单元测试执行。当前 JSON Schema 尚不是每个嵌套字段和跨文件关系的完整形式化证明，不能仅凭“schema 文件是合法 JSON”宣称全部数据契约已经验证。
