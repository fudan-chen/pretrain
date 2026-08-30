# Marin 公开训练追踪与学习系统

这个仓库把 Marin 的公开工程证据、535B-A23B Hero Run 指标和 Scaling Ladder 方法组织成一套**可复查、可复算、可学习**的中文资料。

当前集成分支先并列保留两套已有成果：

- `main` 的公开证据快照、失败语义和每日生态摘要；
- `marin-deep-track` 的 Hero 指标、旧看板、旧日报和长篇复盘。

旧分支和旧页面暂不删除或改写，便于对照。后续新增的 v2 方法、文档与站点会使用独立目录，并明确区分 `OBSERVED`、`DERIVED` 和 `INFERRED`，旧页面不再被当作当前权威结论。

## 现有入口

- 公开证据采集：`scripts/track_marin.py`
- Hero 指标采集：`scripts/pull_data.py`、`scripts/track_hero.py`
- 旧版看板：`dashboard/`
- 旧版 Scaling Ladder 复盘：`reports/ladder/`
- 旧版 Hero 日报：`reports/daily/`
- 生态证据日报：`notes/daily/`

## 数据原则

1. 原始证据尽量不可变，并记录来源状态与时间窗口。
2. 派生结论必须指向输入、算法版本和可复现命令。
3. 推断必须说明置信度、替代解释和可能推翻它的证据。
4. Train CE 与 held-out Paloma loss 等不同统计量不做数值上的直接比较。
5. 实际 run config 的事实优先级高于 issue 叙述和二手总结。

## 基础验证

代码只依赖 Python 标准库，支持 Python 3.9 及以上版本。提交前运行：

```bash
python -m unittest discover -s tests -v
python -m compileall -q scripts tests
```

## 历史分支

- [`main`](https://github.com/fudan-chen/pretrain/tree/main)：公开证据采集主线。
- [`marin-deep-track`](https://github.com/fudan-chen/pretrain/tree/marin-deep-track)：第一版深度追踪与展示。
- [`codex/cloud-marin-tracker`](https://github.com/fudan-chen/pretrain/tree/codex/cloud-marin-tracker)：最初的云端工作流尝试。

这些分支暂时保留，供方法、代码和展示方式的前后对比。
