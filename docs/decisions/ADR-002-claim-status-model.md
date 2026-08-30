# ADR-002：页面只渲染 typed claims

- 状态：Accepted
- 日期：2026-08-30

## 背景

v1 HTML 同时承担数据读取、分析、绘图和解释，导致“数据已更新、文字仍陈旧”。TPU、cosine/WSD、25% milestone 等错误都能长期留在“实时”页面。

## 决策

页面只消费：

```text
current_status.json
claim_ledger.json
```

Claim 分为：

- OBSERVED：直接证据。
- DERIVED：确定性方法。
- INFERRED：带置信度、替代解释和反证条件的判断。

`render.py` 不得重新计算 scaling prediction，也不得根据硬编码百分比生成科研结论。

## 后果

- 没有合法 Claim 时，页面显示 unavailable/insufficient evidence。
- 每张 ClaimCard 文字显示等级，不只依赖颜色。
- 解释更保守，但审计性、可维护性和教学价值提高。
