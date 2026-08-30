# 运维手册 · marin-deep-track

> 本文件记录这套追踪系统的**细小但容易踩坑的注意事项**。改代码/改 workflow/人工排查前请先读对应小节。
> 最后更新：2026-08-28（随系统演进持续补充）。

---

## 0. 架构速览（双分支模型）

| 分支 | 内容 | 为什么 |
|---|---|---|
| `main` | 仅 `.github/workflows/hero-track.yml`（+ 用户原有的 track-marin 系统） | GitHub **schedule 只从默认分支读取** workflow 定义 |
| `marin-deep-track` | 全部脚本 / 数据 / 日报 / dashboard / 复盘报告 | 数据与代码的工作分支，workflow 运行时 checkout 此分支 |

**推论**：修改 `hero-track.yml` 后必须**同时合入 main** 才会被定时器按新逻辑执行；只推 marin-deep-track 不影响 schedule 行为。

---

## 1. 定时机制注意事项

- cron `0 0,12 * * *`（UTC）= 北京时间 **08:00 / 20:00**。GitHub cron 无北京时间概念，换算已固化，勿直接写 `0 8,20`。
- **GitHub schedule 不保证准时**：高负载时段延迟 10–60 分钟属常态（2026-08-28 北京 20:00 档即未准点出现）。需要准点数据时用 `workflow_dispatch` 手动补触发：Actions → hero-track → Run workflow → 分支选 **main**。
- 手动触发 dispatch 的 `ref` 必须填 `main`（workflow 定义所在分支）；实际 checkout 的仍是 marin-deep-track。
- **GitHub 规则**：仓库 60 天无任何活动会自动禁用 schedule workflow。本仓库另有 `track-marin.yml` 每日 02:17 UTC 运行（main 上用户原有的证据采集系统），整体风险低；但若那个系统停了，记得每 60 天内手动触发一次。
- 两套系统完全独立：`track-marin.yml`（每日证据采集）与 `hero-track.yml`（hero run 指标追踪）互不读写对方文件，**不要合并、不要互相改**。

## 2. 数据口径（最容易出错的一组）

- **MFU 原始值就是百分比**：W&B 里 21.0 即 21%，**不要再 ×100**（×100 会得到 2096 这种荒谬值，历史上踩过）。
- **eval 每 ~3000 步一次**（eval.jsonl 只有约每 3000 步一个点）。窗口内无新 eval 时，日报显示「本窗口无新 eval 点」+ 当前进度预测参考值，这不是故障。
- **step-0 的 eval（CE≈11.79）是随机初始化基线**，判断预测偏差时必须跳过（脚本已处理：只用 step>0 的 eval）。若改脚本，保留此口径。
- **冷启动前 200 步不参与异常检测**（loss/吞吐的瞬态会误报），改检测阈值时勿去掉这个过滤。
- **train CE（分布内训练损失）与 dropless paloma macro（评测集）是两个口径**，绝对值不可直接比较（当前约 1.28 vs 2.29 是正常的）。对比预测一律用 eval 口径。
- 日报的 `eval_gap` = 训练态 eval − 该步数幂律预测；**负值 = 优于预测**，正值 = 高于预测。
- tokens 估算 = step × `HERO_TOKENS_PER_STEP`；速率/ETA 由窗口差分估计，日间波动 ±20% 正常。

## 3. 数据流注意事项

- **mixture.jsonl 只在权重变化时新增行**（W&B 按变化记录）。当前仅 step 0 的 stage-0 快照（200 个权重 = 40 簇 × 5 质量桶）。**80% 进度（step ≈ 312,200）phase-2 切换时会自动出现新行**，dashboard 的配比快照与 `mixture/stage` 会自动更新——**无需改任何代码**，但届时应人工核对一次 stage 值是否如期变为 1。
- router.jsonl 为 2000 点降采样；dashboard 只取聚合键（`bias_max`、`capacity_overflow_rate_mean`）。**分层明细（layer_0..47）在原始 jsonl**，排查负载不均衡时直接查它。
- system_metrics.json 是 W&B **累计快照**（非时序）：NVLink/PCIe = 0 表示**未插桩**（不是没有），通信带宽结论以官方 EP 文档实测为准；power/temp 为真实读数。
- `pull_hero_system.py` 现已加入 workflow（带 `||` 容错），每次定时运行顺带刷新 system_metrics.json；失败不阻塞主流程。
- **backfill 是幂等全量重写**：每次运行重生成所有「完整 12h 窗口」的日报。W&B 补写迟到指标时，历史日报会自动微调——这是特性不是 bug；`_index.json` 始终与日报一致。
- W&B 匿名 GraphQL 无 API key，存在限流可能。单次拉取失败**不影响下一窗口**（每次都是全量拉取）；连续失败再查 marin_wandb.py 的 GraphQL schema 是否变更。
- eval.jsonl 实际包含 **16 域 paloma 明细**，dashboard 目前只用 macro 值。**可扩展点**：域级曲线能更早暴露偏科/涌现差异。
- 窗口命名按**北京时间窗口端点**：UTC 00:00 结束 → `-am`（北京 08:00），UTC 12:00 结束 → `-pm`（北京 20:00）。若改窗口逻辑，保持这个命名约定（历史上因对齐错误导致全 `-pm` 的 bug）。

## 4. 里程碑盯梢清单（人工 + 自动结合）

| 里程碑 | 位置 | 信号 | 动作 |
|---|---|---|---|
| grad-norm 峰值区 | ~25%，step ≈ 97,562 | 对比 ladder 四档同进度的 grad 签名 | 人工写分析（日报有阈值检测，但「是否符合 ladder 签名」需人看） |
| **loss 二次下降** | 无预定位置 | CE/eval 曲线第二段下弯 | ⚠️ **未规则化，纯人工盯**：看日报 eval_gap 趋势 + dashboard 曲线形态 |
| **涌现效应** | 无预定位置 | 某些域 eval 突降 | ⚠️ dashboard 仅 macro；需查 eval.jsonl 的 16 域明细（见 §3 可扩展点） |
| phase-2 配比切换 | 80%，step ≈ 312,200 | mixture/stage 0→1，权重行新增 | 自动捕获；届时人工核对 stage 值 + 更新复盘报告 |
| run 结束/中止 | — | meta.state 变化、heartbeatAt 停更、吞吐归零事件 | workflow 会输出 "no changes"；人工确认后写终章复盘 |

## 5. Dashboard 与报告访问

- **在线（推荐，实时）**：
  - Dashboard：https://fudan-chen.github.io/pretrain/dashboard/
  - 复盘报告：https://fudan-chen.github.io/pretrain/reports/ladder/
  - Pages source = marin-deep-track 分支根目录，推送后 1–10 分钟自动部署。
- **备选**：`https://htmlpreview.github.io/?https://github.com/fudan-chen/pretrain/blob/marin-deep-track/dashboard/index.html`
- ⚠️ **repo 版 `dashboard/index.html` 用 `fetch('hero_data.json')` 取数，本地 `file://` 双击打开会被浏览器 CORS 拦截** → 用 Pages 链接，或本地 `python -m http.server` 后访问。
- ⚠️ artifact 版（`/mnt/cos/artifacts/*.html`，数据内联自包含）是**生成时刻的快照，不自动更新**；看实时数据永远以 Pages 版为准。
- MD 版复盘报告（`reports/ladder/scaling_ladder_report.md`）是**摘要**；完整 10 章节版是 `reports/ladder/index.html`（及同名 artifact）。

## 6. 安全

- 本任务使用过 PAT 直接推送，该 token 曾出现在对话与沙箱脚本中。**任务阶段性结束后建议轮换/吊销**，重新生成仅 `repo` 权限的新 token。
- workflow 内只用 `GITHUB_TOKEN`（`permissions: contents: write`），**不要把 PAT 提交进仓库**；当前仓库全文检索应无 `ghp_` 串（改动前自查）。
- `.gitignore` 已挡 `__pycache__/`、`*.pyc`；workflow 用 `git add -A`，新增文件类型前确认无敏感物。

## 7. 故障处理速查

| 症状 | 可能原因 | 处理 |
|---|---|---|
| Actions run 失败 | W&B 限流/网络抖动 | 看日志；多为瞬时，下一窗口自愈；连续失败查 GraphQL schema |
| push 报 non-fast-forward | 人工同时推了 marin-deep-track | 重跑 workflow（每次 fresh checkout，force=False 不会覆盖他人提交） |
| Pages 404 | 构建中或 source 被改 | 等 1–10 分钟；Settings → Pages 确认 source=marin-deep-track / |
| 日报缺某个窗口 | 该窗口不是「完整 12h 窗口」（数据时间戳未跨过窗口终点） | 正常现象；下次运行自动补齐 |
| dashboard 图空白 | hero_data.json 缺失/字段变更 | 检查 workflow 日志的 dashboard 步骤；本地 JSON 校验 |
| mixture 权重和 ≠ 1 | 权重是归一化前的原始值 | 当前实现已归一化（sum=1.0）；若偏离 >1e-3 需查上游 |

## 8. 文件地图

```
scripts/
  marin_wandb.py        # W&B 匿名 GraphQL 客户端（sampledHistory/systemMetrics/historyKeys）
  pull_data.py          # 按模式拉时序：hero=dense/eval/mixture/system/router
  pull_hero_system.py   # 系统遥测累计快照（已挂入 workflow，容错执行）
  track_hero.py         # 追踪主控：update（拉+检测+日报）/ backfill / dashboard
data/hero/hero-12d8b6f0-dee637/
  dense.jsonl eval.jsonl mixture.jsonl router.jsonl system_metrics.json meta.json
reports/
  ladder/               # 任务一复盘：index.html（完整）+ scaling_ladder_report.md（摘要）+ figs/
  daily/                # 任务二日报：YYYY-MM-DD-am|pm.md + _index.json
dashboard/
  index.html            # fetch 版（Pages 用）
  hero_data.json        # 看板数据（track_hero.py dashboard 生成）
docs/OPERATIONS.md      # 本文件
.github/workflows/hero-track.yml   # 定时定义（main 与 marin-deep-track 需保持同步）
```
