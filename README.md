# Marin 公开进展追踪

这个仓库每天采集 Marin 的公开工程证据，保存可复查的来源快照，并生成一份中文日报。GitHub Actions 默认在每天 **02:17 UTC** 运行；采集日期默认是运行时的**前一个 UTC 自然日**。

## 数据来源

一次采集包含四类上游来源：

1. [`marin-community/marin`](https://github.com/marin-community/marin) 的 GitHub Issues，以及每个 Issue 的全部评论；
2. 同一 GitHub 仓库的 commits；
3. Hugging Face 上 [`marin-community`](https://huggingface.co/marin-community) 组织公开的 models 与 datasets；
4. [`https://marin.community/`](https://marin.community/) 官网快照。

GitHub Issue 证据会保留正文与评论的作者、创建/更新时间和原始链接，便于回看事故、恢复过程、踩坑记录与维护者经验。

## 输出结构

每个目标日期对应一组证据快照和一份日报：

```text
data/
└── snapshots/
    └── YYYY-MM-DD/
        ├── manifest.json        # 采集时间及各来源的成功/失败状态
        ├── github_issues.json   # Issues、正文与全部评论
        ├── github_commits.json  # 指定 UTC 窗口内的 commits
        ├── hugging_face.json    # models 与 datasets
        └── marin_site.json      # 官网 HTML、链接与内容哈希
notes/
└── daily/
    └── YYYY-MM-DD.md            # 当日中文摘要
```

首次采集时只有成功来源会生成对应的证据 JSON；失败详情记录在 `manifest.json`。同一天再次运行时，已有成功 JSON 默认不可变，脚本只补采此前缺失的来源；manifest 会以 `preserved_evidence` 标明复用证据及其原始采集时间。这样上游后来删除或改写内容，也不会让重跑抹掉既有审计证据。工作流只会提交 `data/snapshots/` 和 `notes/daily/` 中的新变化，没有变化时不会创建空提交。

Issue 和 Hugging Face 元数据是可变记录：一条目标日发生过活动的记录，可能在跨过 UTC 午夜后再次更新。脚本因此从目标日结束继续观察到实际采集时刻（最长重叠一天），并把跨午夜记录单列为 `spillover_*`，不计入目标日汇总；相邻快照可能出现同一记录，以避免午夜附近的工程证据漏采。

## 运行方式

脚本只使用 Python 标准库，支持 Python 3.9 及以上版本；GitHub Actions 固定使用 Python 3.12。默认采集前一 UTC 日：

```bash
python scripts/track_marin.py
```

也可以指定日期：

```bash
python scripts/track_marin.py --date 2026-08-23
```

目标日期必须是已经结束的 UTC 自然日，脚本会拒绝今天或未来日期，防止不完整快照被后续运行误认为完成。

设置 `MARIN_GITHUB_TOKEN`（或 `GITHUB_TOKEN`）可以提高 GitHub API 限额；GitHub Actions 默认使用本次运行的 token。若该安装令牌不允许读取目标公开仓库，脚本会自动回退到匿名读取；也可以把只读 token 保存为可选仓库 Secret `MARIN_GITHUB_TOKEN`：

```bash
MARIN_GITHUB_TOKEN=… python scripts/track_marin.py
```

提交前可运行与云端相同的检查：

```bash
python -m unittest discover -s tests -v
python -m compileall -q scripts tests
```

## 来源失败时的语义

- **部分失败**：只要至少一个来源成功，脚本就会发布快照和日报；失败来源及错误会如实写入 `manifest.json`。如果同日已有成功证据，失败来源的旧证据会保留并明确标记，便于后续补采或排障。
- **全部失败**：默认退出码为 `2`，清理临时结果，不发布该日期的快照或日报。GitHub Actions 会立即失败，因此后续 commit/push 步骤不会执行，不会把全失败记录误当成训练证据。
- **排障模式**：`--allow-total-failure` 允许全来源失败时仍落盘失败记录；已有成功证据仍不会被删除。它只适合诊断，不应加入每日定时工作流。

例如：

```bash
python scripts/track_marin.py --date 2026-08-23 --allow-total-failure
```

如确实要主动重抓并替换同日已有成功证据，必须显式使用 `--refresh-existing`。这是可能改变历史快照的维护操作，不会出现在定时工作流中：

```bash
python scripts/track_marin.py --date 2026-08-23 --refresh-existing
```

## 首次启用云端运行

1. 确保代码和 `.github/workflows/track-marin.yml` 已在默认分支 `main`。定时任务只会从默认分支读取工作流。
2. 打开仓库的 **Actions → Track Marin → Run workflow**，先手动运行一次。日期留空会按该次 workflow run 的创建时间采集前一 UTC 日，也可以输入 `YYYY-MM-DD` 补采指定日期；重跑同一个失败 run 时日期不会漂移到下一天。
3. 工作流会先执行单元测试和语法编译，再采集上游。成功且输出有变化时，由 `github-actions[bot]` 自动 commit 并 push 到当前分支。
4. 工作流声明了 `contents: write`。如果 push 仍返回 403，请在 **Settings → Actions → General → Workflow permissions** 中允许读写，并检查默认分支保护规则是否允许 GitHub Actions 写入。

`GITHUB_TOKEN` 由 GitHub Actions 自动创建，无需把个人访问令牌保存到仓库。并发队列会让多次采集顺序运行；提交前还会基于最新远端分支 rebase，降低运行期间其他提交导致的 push 冲突。

GitHub 的 cron 使用 UTC，繁忙时可能延迟。对于公开仓库，如果连续 60 天没有仓库活动，GitHub 可能自动停用 scheduled workflow；届时可在 Actions 页面重新启用，或提交一次工作流变更后再手动验证。

---

> 🔬 **Marin 535B 深度追踪**：Scaling Ladder 复盘报告 + 每日两次（北京 08:00/20:00）自动追踪日报 + 实时看板 → 见 [`marin-deep-track`](https://github.com/fudan-chen/pretrain/tree/marin-deep-track) 分支；在线看板 <https://fudan-chen.github.io/pretrain/dashboard/> · 完整复盘 <https://fudan-chen.github.io/pretrain/reports/ladder/>
