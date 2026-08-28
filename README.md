# marin-deep-track

> 对 Marin（Stanford Percy Liang / Simile AI）**535B-A23B MoE** 全网公开训练的深度追踪与技术复盘。
> 与 `codex/cloud-marin-tracker` 分支（仅记录链接变动）不同，本分支提供**原始指标重绘的曲线、逐层分析与定时自动追踪**。

## 🌐 在线访问（GitHub Pages，推送后自动部署）

- **追踪看板（实时）**：https://fudan-chen.github.io/pretrain/dashboard/
- **复盘报告（完整版）**：https://fudan-chen.github.io/pretrain/reports/ladder/

> ⚠️ `dashboard/index.html` 通过 `fetch('hero_data.json')` 取数，**本地 `file://` 双击会被浏览器 CORS 拦截**——请用上面的 Pages 链接，或本地 `python -m http.server` 后访问。

## 两件交付

### 任务一 · Scaling Ladder 深度复盘（已完成）
📄 **完整版 `reports/ladder/index.html`**（10 章节，自绘 8 图 + 官方 6 图）· 摘要版 `reports/ladder/scaling_ladder_report.md`
四级 Scaling Ladder（1.6B→27.7B）的完整技术复盘：
实验设计 / 训练曲线全景 / stable-decay 阶段切分 / 数据配比与顺序 / Paloma 16 域 benchmark /
报错修复编年史 / 硬件通信 MoE 监控 / **缩放定律独立复算（官方预注册 ≈2.04，本文复算 2.070）**。

### 任务二 · Hero Run 定时追踪（进行中）
📊 `dashboard/index.html` — 535B 主训练（`hero-12d8b6f0-dee637`）实时看板：loss 曲线 vs Ladder 预测、
grad norm 健康签名、MoE 路由负载、数据配比快照、吞吐 / MFU。
🗓️ `reports/daily/` — 每天 08:00 / 20:00（北京时间）自动生成的追踪日报 + `_index.json` 索引。
🛠️ **运维手册 [`docs/OPERATIONS.md`](docs/OPERATIONS.md)** — 数据口径、定时机制、里程碑盯梢清单、故障处理等细小注意事项（**改代码 / 排查前必读**）。

## 目录

```
scripts/                 # 抓取与分析（纯 stdlib，匿名读公开 wandb GraphQL）
  marin_wandb.py         #   wandb 匿名客户端（sampledHistory/systemMetrics/...）
  pull_data.py           #   按模式拉取 run 的 dense/eval/mixture/system/router 时序
  pull_hero_system.py    #   系统级遥测（NVLink/PCIe/power/temp 累计快照）
  track_hero.py          #   hero 定时追踪主控（抓数→事件检测→日报→看板数据）
data/                    # 落盘的时序与分析中间件
reports/
  ladder/                # 任务一：复盘（index.html 完整版 + .md 摘要 + figs/）
  daily/                 # 任务二：每日追踪日报（Markdown）+ _index.json
dashboard/               # 汇总看板（index.html + hero_data.json）
docs/                    # 运维手册（OPERATIONS.md）
.github/workflows/       # 定时任务（北京时间 08:00 / 20:00；改动需同步合入 main）
```

## 数据源（全部公开）
- W&B 项目 `marin-community/marin_moe`（[报告页](https://wandb.ai/marin-community/marin_moe/reports/535B-A23B-18T-Token-Hero-Run-Scaling-Ladder--VmlldzoxNzc2MDM5Ng)）
- [marin issue #8435](https://github.com/marin-community/marin/issues/8435)（hero run 追踪）
- marin 仓库 `experiments/grug/moe_hero_ep/`（@d23e6e9c）
- [数据配比页](https://storage.googleapis.com/marin-public/held/harrier-k40-cluster-overview/2026.08.18/index.html?revision=uniform-sampling) · [EP 实现文档](https://storage.googleapis.com/marin-public/rav/moe-fixed-wave-a2a-384/2026.08.17/index.html)

*本仓库为独立技术分析，所有指标经原始时序重绘；与官方预注册值并列呈现。*
