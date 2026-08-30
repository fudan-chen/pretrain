# ADR-003：Baseline 适用性必须是可执行门禁

- 状态：Accepted
- 日期：2026-08-30

## 背景

仅在文档写“recipe 改变后应重新评估”无法阻止自动任务继续发布旧 residual。缺字段也不能默认等于匹配。

## 决策

Baseline 保存 machine-readable requirements：run ID、context length、注册 steps、tracker group 和 datamix revision。Phase 1 的固定期望分别是：

```text
run ID          = hero-12d8b6f0-dee637
context length  = 4096
registered steps= 390251
tracker group   = moe-hero-ep-scaling-ladder
datamix tag     contains harrier-mix-2026.08.18
```

分析前逐项与 run meta 比较：

```text
all match      → supported → 允许比较
any mismatch   → mismatch  → 抑制比较
any missing    → unverified → 抑制比较
```

`matched_progress`、residual 序列、日报和页面全部消费同一个 gate 结果。

## 后果

- Recipe 变更不会静默沿用旧 baseline。
- 缺失证据不再被“乐观默认”。
- 新 regime 必须登记新 requirement 或 baseline 版本。
- `scripts/audit_v2.py` 与故障注入测试负责防回归。
- Gate 只证明已登记字段相符，不证明所有未登记训练细节都相同；增加新的关键 recipe 维度时必须扩展 requirement。

## 验证

```bash
python scripts/audit_v2.py
python scripts/audit_v2.py --context-length 8192
python -m unittest tests.test_hero_analysis.HeroAnalysisTests.test_baseline_applicability_is_executable -v
```

正常 evidence 应为 `supported`；8192 注入应为 `mismatch`；删除 context 字段的测试应为 `unverified`。后两者都必须抑制 comparison，而不是只显示 warning。
