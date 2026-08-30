# v2 维护手册

## 安全边界

- `main`、`marin-deep-track`、`codex/cloud-marin-tracker` 暂不删除。
- `build` 只重建 `data/baselines/`、`data/derived/`、`reports/generated/hero/` 和 `site/`，不访问网络。
- `update` 还会刷新 `data/hero/<run>/`；只在明确需要新 Hero evidence 时运行。
- `collect_ladder_grid.py` 会刷新 `data/ladder/source/`、`data/ladder_eval_grid.json` 与 manifest；它是独立的显式网络操作，不属于普通 build。
- 旧 `dashboard/`、`reports/daily/`、`reports/ladder/` 不由 v2 构建覆盖。
- 在验证稳定前，v2 workflow 只允许手动运行，不与旧 schedule 抢写路径。

## 本地构建

```bash
python scripts/track_hero.py build
python -m unittest discover -s tests -v
python -m compileall -q scripts tests
```

启动预览：

```bash
python -m http.server 8000 --directory site
```

访问 `http://127.0.0.1:8000/`。

`site/` 必须能单独工作：课程、参考资料、日报和 evidence 定位页已经渲染进站点，完整 Claim evidence 位于 `site/artifacts/`。不要用仓库根目录服务器掩盖逃出 `site/` 的坏链接。

## 刷新公开 W&B 数据

```bash
python scripts/track_hero.py update
```

`update` 会先运行现有 `pull_data.pull_run()`，再重建 v2 派生内容。仅重建时使用 `build`，避免无意触发网络请求。

## 刷新 Ladder rung evidence

只有在明确要建立新 evidence 版本时运行：

```bash
python scripts/collect_ladder_grid.py
python scripts/track_hero.py baseline
python -m unittest tests.test_ladder -v
git diff -- data/ladder data/ladder_eval_grid.json data/ladder_eval_grid.manifest.json data/baselines
```

Collector 使用 W&B `sampledHistory`，重新采集不保证与旧 checksum 相同。重点审查：四个 display name/run ID、`stop_after_steps`、每个 source SHA、选中行数、grid SHA 和 5%/10%/100% fixture。

Collector 会先把四个 rung 全部取回并验证，再进入文件发布阶段，因此中途网络失败不会覆盖旧 evidence。多文件落盘仍不是文件系统级事务；若发布阶段发生磁盘错误，不要 stage、build 或发布，必须重新完整采集并核对 manifest。

## 运行反证门禁

```bash
python scripts/audit_v2.py
python scripts/audit_v2.py --context-length 8192
python scripts/audit_v2.py --simulated-residual 0.1
python scripts/audit_v2.py --simulated-residual -0.1
```

正常 evidence 应得到 applicability=`supported`。8192 注入应得到 `mismatch`；自动分析遇到同类 mismatch/unverified 时必须令 `matched_progress=null`。正负 residual 注入必须改变推断方向，不能复用固定乐观文案。详见 [`07 · 反证实验室`](../learning/07-falsification-lab.md)。

## 发布前检查

1. `tests/test_ladder.py` 的 5%/10%/100% fixture 通过。
2. step 32,999 canonical residual 为约 `-0.06838583`；显示值是 `-0.06839`，不得用截断值制造另一个权威结果。
3. Applicability 五项为 `match`；mismatch/unverified fixture 会抑制 comparison。
4. `tests/test_hero_analysis.py` 验证 `linear / GB200 / 704 configured slots` 与方向切换。
5. `track_hero.py --help` 返回 0，非法命令非零。
6. `site/learn/07-falsification-lab/index.html` 和所有日报详情已生成。
7. `python scripts/check_site.py` 无内部 404、path escape、`{{TOKEN}}` 或缺 anchor。
8. 390、768、1280、1440 宽度检查首页、状态页、课程、表格与公式。
9. 每个 SVG 有 `<title>` 和 `<desc>`，每张数据图有表格。
10. `claim_ledger.json` 全部通过 Claim lint；Claim 能点击到 `site/evidence/` 定位页，完整文件能在 `site/artifacts/` 与 catalog 中找到。
11. `rg 'A_FIT|ALPHA_FIT|C_FULL_HERO \*' scripts` 为空。
12. 常见 token 扫描无敏感串。

## 双跑策略

1. 旧 schedule 保持写旧分支/旧路径。
2. v2 先由 workflow dispatch 手动跑，只写 v2 路径。
3. 比较至少两个完整定时周期：数据时间、报告数、Pages 链接、Claim 方向。
4. 确认无漂移后，再讨论切换 Pages 主入口和 schedule。
5. 本阶段不删除旧分支。

双跑验收只覆盖 Phase 1：matched-progress、gating、日报、课程和自包含站点。不要把两个成功周期表述成 Paloma domain、全层 Router、datamix、通信归因或统计显著性已经验证。

## 失败语义

- Collect 失败：不重建成“新鲜”页面；保留旧 evidence 的 `data_as_of`。
- Ladder collector 网络读取失败：发布阶段尚未开始，旧 evidence 保持不变；若多文件落盘阶段发生磁盘错误，重新完整采集并核对 manifest 后才能发布。
- Analyze 失败：不发布一半新的 status/claims。
- Render 失败：旧站点继续可用。
- Recipe mismatch：applicability=`mismatch`，matched-progress comparison 为 unavailable；先登记新 regime/baseline。
- Recipe 字段缺失：applicability=`unverified`，同样抑制 comparison，不能默认匹配。
