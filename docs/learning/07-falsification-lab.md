# 07 · 反证实验室：主动让系统失败

## 本章问题

如果一个分析系统只在“当前这份数据”上给出正确答案，我们仍不知道它遇到 recipe 改变、方向翻转或缺字段时会不会继续讲旧故事。

v2 Phase 1 把三个关键反证场景做成只读命令和故障注入测试。开始前应先理解 [`02 · Scaling law 不是 learning curve`](02-scaling-law-is-not-learning-curve.md) 和 [`05 · 敏感性不是置信区间`](05-uncertainty-and-limits.md)。

## 当前实验覆盖

| 实验 | 改变什么 | 合格结果 | 不会改变什么 |
|---|---|---|---|
| 当前 applicability | 不注入 | 五项 requirement 全部 `match` | 仓库 evidence |
| context mismatch | 临时把 4096 改为 8192 | gate=`mismatch`，比较被抑制 | `meta.json` |
| residual 方向 | 临时注入正、负、零 residual | 推断文案随方向变化 | 原始 eval 与 baseline |

这些命令只把副本放在内存中审计，退出后不会写文件。

## 实验一：检查当前 baseline 适用性

```bash
python scripts/audit_v2.py
```

输出中的 `applicability.checks` 必须逐项显示 selector、expected、observed 和 result。只有全部为 `match`，status 才是 `supported`，系统才允许生成 residual。

当前门禁检查 run ID、4096 context、注册步数、tracker group 和 Harrier datamix tag。任一字段缺失时是 `unverified`，而不是乐观地当作 match；任一值不一致时是 `mismatch`。

## 实验二：模拟 context length 改变

```bash
python scripts/audit_v2.py --context-length 8192
```

预期：`context_length` 检查变为 `mismatch`。这个命令只审计 predicate，不修改仓库 evidence。自动管道中的同类 mismatch 会令 `matched_progress=null`，而不是沿用 4k baseline。

对应测试：

```bash
python -m unittest tests.test_hero_analysis.HeroAnalysisTests.test_baseline_applicability_is_executable -v
```

这条测试还覆盖“字段缺失 → unverified”和“不兼容 baseline → `matched_progress=null`”。门禁设计记录在 `docs/decisions/ADR-003-baseline-applicability-gate.md`；这里保留为纯文本路径，避免自包含站点链接逃出 `site/` 发布根。

## 实验三：模拟 residual 方向翻转

```bash
python scripts/audit_v2.py --simulated-residual 0.1
python scripts/audit_v2.py --simulated-residual -0.1
python scripts/audit_v2.py --simulated-residual 0
```

三次输出的 `simulated_interpretation` 必须分别写“实测高于”“实测低于”“参考相同”。这样可以防止数值更新后，页面仍发布固定的乐观文案。

## 敏感性符号检查

`residual_sensitivity_range` 的定义是：

```text
low  = actual - prediction_sensitivity_high
high = actual - prediction_sensitivity_low
```

若整个范围都小于零，只能说 residual 方向对当前 leave-one-rung-out 选择稳健；它仍不是统计置信区间。若范围跨零，应明确写“方向对 rung 选择敏感”。

## 反证与失败的区别

- 测试失败：实现没有满足已声明契约。
- Claim 被反证：新 evidence 与原 Claim 冲突。
- Evidence 不足：缺字段、数据陈旧或 regime 未验证，不能把它偷换成 match。

一个可靠系统不追求“永远给结论”，而是能在不能比较时稳定地输出 unavailable。

## 尚未覆盖的反证

当前命令还不能完成以下实验：

- 对不同 asymptote 和 d2048 外推策略生成完整敏感性矩阵；
- 用小 rung 回测被省略 rung 的覆盖表现；
- 证明 server-sampled history 没有漏掉短时异常；
- 验证 Paloma 16 域、完整 48 层 Router、datamix delta 或系统通信因果。

因此，本章证明的是“Phase 1 的关键门禁和文案不会在已测试场景下静默沿用”，不是“整个训练解释已经无法被推翻”。

## 自测

1. `unverified` 为什么不能降级成 warning 后继续生成 residual？
2. residual 敏感性范围全部为负，最多能支持什么表述？
3. 为什么重新运行 rung collector 不属于本章的只读故障注入？

答案：缺字段意味着适用性尚未建立；只能说方向对当前 LOO 选择稳健而不能说统计显著；collector 会访问外部源并刷新 evidence 文件。
