# Marin 公开训练追踪与学习系统

这个仓库把 Marin 的公开工程证据、535B-A23B Hero Run 指标和 Scaling Ladder 方法组织成一套**可复查、可复算、可学习**的中文资料。

v2 的重点不是增加更多图，而是让每条结论都回答：

```text
它是直接观测、确定性计算，还是解释性推断？
用了什么输入与方法？
什么证据可能推翻它？
```

## 已验证的 worked example

- 下列数值固定记录 step 32,999 的可复现实例，不代表网站的最新状态；实时结果以 [`site/`](site/) 和 [在线站点](https://fudan-chen.github.io/pretrain/) 为准。
- 官方逐 5% 方法复现值：5% `2.39209261`、10% `2.32614272`、100% `2.03878460`。
- step 32,999 的 Paloma 原始实测为 `2.2781243324279785`。
- matched-progress 点预测为 `2.34651016`。
- residual `actual − prediction = -0.06838582505660584`，即实测低于点预测。
- 当前只有点估计与 leave-one-rung-out 敏感性范围，**不能声称统计显著领先或保证终点达标**。

v2 第一阶段把 **Scaling Ladder、同进度 Paloma 比较与证据纪律**做成闭环。Router、datamix 和系统信号目前是阅读边界与后续课程，不冒充已经完成的因果分析。

## 三条入口

- 新读者：[`docs/learning/00-start-here.md`](docs/learning/00-start-here.md)
- 学方法：[`docs/learning/02-scaling-law-is-not-learning-curve.md`](docs/learning/02-scaling-law-is-not-learning-curve.md)
- 看全目录：[`docs/README.md`](docs/README.md)

生成后的 v2 站点入口是 `site/index.html`。它有开始、状态、学习、方法、日报和版本对比六个主入口，并把八章课程、参考文档、日报和 Claim evidence 分别生成可直接访问的详情页。

## 一条命令重建

代码只依赖 Python 标准库，支持 Python 3.9 及以上版本：

```bash
python scripts/track_hero.py build
python -m unittest discover -s tests -v
python scripts/check_site.py
```

`build` 不访问网络。需要刷新公开 W&B evidence 时使用：

```bash
python scripts/track_hero.py update
```

需要从四个公开 rung 重新采集 grid 时，显式运行：

```bash
python scripts/collect_ladder_grid.py
python scripts/track_hero.py build
```

该命令会保存 `data/ladder/source/*.jsonl` 和采集 manifest；普通构建不会偷偷刷新它们。

本地预览：

```bash
python -m http.server 8000 --directory site
```

## 代码与数据流

```text
公开源
  ├─ track_marin.py → data/snapshots/ + notes/daily/
  └─ pull_data.py   → data/hero/<run>/

W&B rung evidence
  → collect_ladder_grid.py → data/ladder/source/ + grid manifest
  → marin_tracker/ladder.py
  → data/baselines/matched_progress_v1.json

evidence + baseline
  → hero.py   → current_status.json
  → claims.py → claim_ledger.json
  → reports.py / render.py
  → reports/generated/hero/ + site/
```

核心模块在 `scripts/marin_tracker/`：

| 文件 | 职责 |
|---|---|
| `config.py` | 固定 run、官方方法和 FLOPs 口径 |
| `io.py` | checksum、原子写入和 metric 序列 |
| `ladder.py` | 每 5% fit、d2048 外推、Hero 插值 |
| `hero.py` | evidence → current status |
| `claims.py` | OBSERVED / DERIVED / INFERRED 契约 |
| `reports.py` | 纠正版 v2 日报 |
| `render.py` | 零运行时依赖的静态 HTML/SVG |
| `cli.py` | collect → analyze → render 编排 |

详细架构见 [`docs/reference/architecture.md`](docs/reference/architecture.md)。

## 新旧内容并列保留

生产切换完成前后，旧分支先作为历史快照保留：

- [`marin-deep-track`](https://github.com/fudan-chen/pretrain/tree/marin-deep-track)：第一版深度追踪与旧 Pages 快照。
- [`codex/cloud-marin-tracker@af5c5f9`](https://github.com/fudan-chen/pretrain/tree/af5c5f9)：最初云端尝试快照。

新分支同时保留以下旧目录，用于逐项比较：

- `dashboard/`
- `reports/daily/`
- `reports/ladder/`
- `docs/OPERATIONS.md`

v2 写入独立目录：

- `data/baselines/`
- `data/derived/`
- `reports/generated/hero/`
- `site/`

完整差异见 [`docs/comparison/v1-v2.md`](docs/comparison/v1-v2.md)。

## 证据规则

1. 原始 evidence 尽量不可变，并记录来源、采样和时间。
2. 派生结论必须指向输入 checksum、算法版本和复现命令。
3. 推断必须说明置信度、替代解释和反证条件。
4. Train CE 与 held-out Paloma loss 不比较绝对值。
5. 来源冲突时：run config / raw metric > pinned source > issue narrative > secondary analysis。
6. `data_as_of`、heartbeat 与构建时间不能混用。

## 发布状态

v2 已通过两个连续的 GitHub Actions 完整周期。合入 `main` 后，workflow 在北京时间 08:00 / 20:00 自动刷新，并从 `site/` 发布 GitHub Pages；也支持手动触发。旧分支只用于历史对照，不再作为新版数据源。
