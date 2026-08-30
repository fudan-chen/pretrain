# v2 架构

## 两条边界：显式联网，默认离线

v2 不把“采集”和“解释”藏在一次隐式运行里：

- `python scripts/track_hero.py build` 是离线、确定性的 analyze → render；只消费仓库内证据。
- `python scripts/track_hero.py update` 先刷新 Hero W&B evidence，再执行 build。
- `python scripts/collect_ladder_grid.py` 是独立的 rung 网络采集命令；普通 build/update 都不会替用户刷新 Ladder 输入。

这样，方法改动可以在不改变 evidence 的情况下复算；刷新外部数据也会留下单独可审查的 diff。

## 端到端数据流

```text
GitHub / Hugging Face / marin.community
  └─ track_marin.py
       └─ data/snapshots/YYYY-MM-DD + notes/daily

Hero W&B public GraphQL sampledHistory
  └─ pull_data.py
       └─ data/hero/<run>/{meta,dense,eval,router,mixture,...}

四个 Ladder rung 的 W&B public GraphQL sampledHistory
  └─ collect_ladder_grid.py                         [显式网络命令]
       ├─ data/ladder/source/{d768,...,d2048}.jsonl
       ├─ data/ladder_eval_grid.manifest.json
       └─ data/ladder_eval_grid.json

固定 grid + manifest + 官方 commit/常数
  └─ marin_tracker/ladder.py                        [离线]
       └─ data/baselines/matched_progress_v1.json
            └─ applicability requirements

Hero meta + baseline requirements
  └─ hero.assess_baseline_applicability
       ├─ supported  → 允许 matched-progress/residual
       ├─ mismatch   → 抑制比较
       └─ unverified → 抑制比较

Hero evidence + gated baseline
  └─ marin_tracker/hero.py
       └─ data/derived/current_status.json
            ├─ claims.py  → claim_ledger.json
            ├─ reports.py → reports/generated/hero/
            └─ render.py  → site/
```

`sampledHistory` 是公开采样证据，不是完整逐步 scan。`data/ladder/source/*.jsonl` 中的“source”表示 collector 实际收到的源记录，不表示它覆盖上游每一个瞬时点。

## 模块职责

| 模块 | 只负责 | 明确不负责 |
|---|---|---|
| `collect_ladder_grid.py` | 定位四个固定 rung、保存采样记录、grid 与 manifest | 离线构建、统计显著性 |
| `config.py` | 固定 run、官方方法常数与 applicability requirements | 页面文案 |
| `io.py` | 读取、checksum、原子写入和 metric 序列 | 科研判断 |
| `ladder.py` | per-5% fit、d2048 外推、LOO、Hero 插值 | W&B 网络请求 |
| `hero.py` | applicability gate；本地 evidence → current status | HTML |
| `claims.py` | typed claims 与运行时验证 | 图表布局 |
| `reports.py` | 从 status/baseline 生成纠正版日报 | 重新实现生态 GitHub 抓取 |
| `render.py` | 静态 HTML/SVG/JSON、Markdown 页面和 evidence 副本 | 重新计算科研结论 |
| `audit_v2.py` | 只读故障注入与方向/适用性审计 | 修改 evidence |
| `check_site.py` | 站内链接、越界链接、模板 token、SVG 可访问性 | 证明科研结论正确 |
| `cli.py` | collect/analyze/render 编排 | 方法实现 |

## 自包含发布包

`render.py` 不再让站点链接逃到仓库根目录：

- `docs/learning/*.md` → `site/learn/<slug>/index.html`；
- `reports/generated/hero/*.md` → `site/daily/<name>/index.html`；
- 当前 Claim 使用的本地 evidence → `site/artifacts/<repository-path>`；
- 每份 evidence → `site/evidence/<artifact-slug>/index.html`，展示 provider、sampling、SHA、定位预览与原始文件入口；
- status、claims、baseline、日报索引 → `site/data/`；
- `site/data/catalog.json` 列出派生数据和可下载 evidence 副本。

因此 `python -m http.server 8000 --directory site` 与只部署 `site/` 具有相同的内部链接语义。读者先进入 HTML evidence 页定位记录，不必直接打开数 MB JSON；完整 artifact 仍保留为复算权威输入。`check_site.py` 会拒绝解析后逃出 `site/` 根的链接，而不只是检查宿主仓库里碰巧存在同名文件。

## 为什么暂不重写 `track_marin.py`

它虽然长，但已有 18 个测试，并实现了分页、精确 UTC 窗口、spillover、部分/全部失败语义、不可变成功证据和原子发布。当前重构优先修复确有方法错误的 Hero 单体脚本，避免为了目录漂亮而扩大风险。

## v2 Phase 1 范围

Phase 1 的完成定义是：Ladder 采样 provenance 可追踪、官方逐 5% 方法可离线复算、baseline applicability 可执行、Claim 有类型、课程/日报/evidence 能作为一个站点发布。

本阶段没有实现：完整 rung/Hero history scan、Paloma 16 域归因、完整 48 层 Router 分析、datamix delta/JSD、change-point 与事故因果链、概率置信/预测区间，以及生产 schedule 或 Pages 主入口迁移。第 06 章描述这些指标的解释边界，不代表相应分析模块已经存在。

## Legacy 共存

以下目录暂不删除：

- `dashboard/`
- `reports/daily/`
- `reports/ladder/`
- `docs/OPERATIONS.md`

新输出使用 `site/`、`reports/generated/hero/` 和 `data/{baselines,derived}/`，因此可以逐文件比较。旧目录属于对照材料，不是 v2 的权威数据接口。
